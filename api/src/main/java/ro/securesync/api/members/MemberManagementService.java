package ro.securesync.api.members;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import ro.securesync.api.security.Actor;

import java.util.*;

@Service
public class MemberManagementService {
    private static final Logger log = LoggerFactory.getLogger(MemberManagementService.class);
    private static final List<String> ALLOWED_ROLES = List.of("USER", "ADMIN", "IMPLEMENTATOR");
    private static final int PAGE_SIZE = 20;
    private final KeycloakMembersGateway gateway;
    private final Object mutationLock = new Object();

    public record Member(String id, String username, String department, List<String> roles, boolean enabled) { }
    public record Page(List<Member> members, int page, boolean hasMore) { }
    public record Access(List<String> roles, String department) { }

    public MemberManagementService(KeycloakMembersGateway gateway) { this.gateway = gateway; }

    public Page list(Actor actor, String search, int page) {
        requireCurrentImplementator(actor);
        String query = search == null ? "" : search.strip();
        if (query.length() > 80 || page < 0 || page > 10000) throw invalid();
        List<ObjectNode> users = gateway.users(query, page * PAGE_SIZE, PAGE_SIZE + 1);
        List<Member> members = new ArrayList<>();
        for (ObjectNode user : users.subList(0, Math.min(PAGE_SIZE, users.size()))) {
            if (serviceAccount(user)) continue;
            String id = targetId(user.path("id").asText());
            members.add(member(user, gateway.effectiveRoles(id)));
        }
        return new Page(List.copyOf(members), page, users.size() > PAGE_SIZE);
    }

    public Member update(Actor actor, String id, Access request) {
        // The fresh authorization check is inside the same lock as mutations: two
        // implementators cannot use stale tokens to remove each other concurrently.
        synchronized (mutationLock) {
            requireCurrentImplementator(actor);
            String target = targetId(id);
            Set<String> desired = validate(request);
            if (target.equalsIgnoreCase(actor.sub())) {
                throw new AccessDeniedException("Propriul acces nu poate fi modificat din acest tab.");
            }
            ObjectNode original = gateway.user(target).deepCopy();
            if (serviceAccount(original)) throw new AccessDeniedException("Conturile de serviciu sunt protejate.");
            List<KeycloakMembersGateway.Role> originalRoles = gateway.directRoles(target);
            Set<String> inherited = names(gateway.effectiveRoles(target));
            inherited.removeAll(names(originalRoles));
            inherited.retainAll(ALLOWED_ROLES);
            if (!inherited.isEmpty()) throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "Membrul are roluri mostenite din grupuri. Modifica asocierea grupului in Keycloak.");

            List<KeycloakMembersGateway.Role> additions = new ArrayList<>();
            Set<String> previous = names(originalRoles);
            for (String name : ALLOWED_ROLES) if (desired.contains(name) && !previous.contains(name)) additions.add(gateway.role(name));
            List<KeycloakMembersGateway.Role> removals = originalRoles.stream()
                    .filter(role -> ALLOWED_ROLES.contains(role.name()) && !desired.contains(role.name())).toList();
            ObjectNode updated = original.deepCopy();
            ObjectNode attributes = updated.withObject("/attributes");
            attributes.putArray("department").add(request.department());
            try {
                gateway.removeRoles(target, removals);
                gateway.addRoles(target, additions);
                gateway.updateUser(target, updated);
                Member result = member(gateway.user(target), gateway.effectiveRoles(target));
                if (!new HashSet<>(result.roles()).equals(desired) || !request.department().equals(result.department())) {
                    throw new ResponseStatusException(HttpStatus.CONFLICT,
                            "Accesul efectiv difera de cel solicitat, posibil din cauza rolurilor mostenite. Reincarca lista.");
                }
                log.info("Member access updated actor={} target={} roles={} department={}", actor.sub(), target, desired, request.department());
                return result;
            } catch (RuntimeException failure) {
                restore(target, original, originalRoles);
                if (failure instanceof ResponseStatusException status && status.getStatusCode().value() == 409) throw status;
                throw KeycloakMembersClient.unavailable();
            }
        }
    }

    private void restore(String id, ObjectNode original, List<KeycloakMembersGateway.Role> originalRoles) {
        // Admin REST operations are not transactional. Re-read after ambiguous
        // failures and restore only this feature's managed roles and department.
        try {
            List<KeycloakMembersGateway.Role> current = gateway.directRoles(id);
            Set<String> before = names(originalRoles);
            Set<String> after = names(current);
            gateway.removeRoles(id, current.stream().filter(role -> ALLOWED_ROLES.contains(role.name()) && !before.contains(role.name())).toList());
            gateway.addRoles(id, originalRoles.stream().filter(role -> ALLOWED_ROLES.contains(role.name()) && !after.contains(role.name())).toList());
            gateway.updateUser(id, original);
        } catch (RuntimeException ignored) {
            log.error("Member access rollback could not be completed target={}; reload actual Keycloak state", id);
        }
    }

    private void requireCurrentImplementator(Actor actor) {
        if (!actor.roles().contains("IMPLEMENTATOR") || !actor.scopes().contains("members:manage")) throw new AccessDeniedException("Acces rezervat implementatorului.");
        String subject;
        try { subject = targetId(actor.sub()); }
        catch (ResponseStatusException invalidSubject) { throw new AccessDeniedException("Identitate invalida."); }
        ObjectNode current;
        try { current = gateway.user(subject); }
        catch (ResponseStatusException missing) {
            if (missing.getStatusCode().value() == 404) throw new AccessDeniedException("Contul nu mai este disponibil.");
            throw missing;
        }
        if (!current.path("enabled").asBoolean(false) || serviceAccount(current)
                || !names(gateway.effectiveRoles(subject)).contains("IMPLEMENTATOR")) {
            throw new AccessDeniedException("Dreptul de implementator nu mai este activ.");
        }
    }

    private static Set<String> validate(Access request) {
        if (request == null || request.roles() == null || request.roles().isEmpty() || request.roles().size() > 3
                || request.roles().stream().anyMatch(role -> role == null || !ALLOWED_ROLES.contains(role))
                || !("IT".equals(request.department()) || "HR".equals(request.department()))) throw invalid();
        Set<String> roles = new LinkedHashSet<>(request.roles());
        if (roles.size() != request.roles().size()) throw invalid();
        return roles;
    }

    private static String targetId(String id) {
        if (id == null || !id.matches("(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")) throw invalid();
        return id;
    }

    private static boolean serviceAccount(JsonNode user) {
        return !user.path("serviceAccountClientId").asText("").isBlank()
                || user.path("username").asText("").startsWith("service-account-");
    }

    private static Member member(ObjectNode user, List<KeycloakMembersGateway.Role> roles) {
        JsonNode department = user.path("attributes").path("department");
        String value = department.isArray() && !department.isEmpty() ? department.get(0).asText("") : "";
        Set<String> names = names(roles);
        return new Member(user.path("id").asText(), user.path("username").asText(), value,
                ALLOWED_ROLES.stream().filter(names::contains).toList(), user.path("enabled").asBoolean(false));
    }

    private static Set<String> names(List<KeycloakMembersGateway.Role> roles) {
        Set<String> result = new LinkedHashSet<>();
        roles.forEach(role -> result.add(role.name()));
        return result;
    }

    private static ResponseStatusException invalid() {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Verifica membrul, rolurile USER/ADMIN/IMPLEMENTATOR si departamentul IT/HR.");
    }
}
