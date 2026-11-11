package ro.securesync.api.members;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.*;
import org.mockito.ArgumentCaptor;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.server.ResponseStatusException;
import ro.securesync.api.security.Actor;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class MemberManagementServiceTest {
    static final String ACTOR = "11111111-1111-4111-8111-111111111111";
    static final String TARGET = "22222222-2222-4222-8222-222222222222";
    static final KeycloakMembersGateway.Role USER = new KeycloakMembersGateway.Role("user-role", "USER");
    static final KeycloakMembersGateway.Role ADMIN = new KeycloakMembersGateway.Role("admin-role", "ADMIN");
    static final KeycloakMembersGateway.Role IMPLEMENTATOR = new KeycloakMembersGateway.Role("implementator-role", "IMPLEMENTATOR");
    static final KeycloakMembersGateway.Role OTHER = new KeycloakMembersGateway.Role("other-role", "unrelated-role");
    KeycloakMembersGateway gateway;
    MemberManagementService service;
    Actor actor;
    ObjectNode target;

    @BeforeEach void prepare() throws Exception {
        gateway = mock(KeycloakMembersGateway.class);
        service = new MemberManagementService(gateway);
        actor = new Actor(ACTOR, "operator", "IT", Set.of("IMPLEMENTATOR"), Set.of("members:manage"));
        target = new ObjectMapper().readValue("""
                {"id":"22222222-2222-4222-8222-222222222222","username":"member","email":"member@securesync.test",
                "firstName":"Demo","lastName":"Member","enabled":true,"emailVerified":true,
                "requiredActions":["VERIFY_EMAIL"],"attributes":{"department":["HR"],"retained":["original"]}}
                """, ObjectNode.class);
        ObjectNode current = target.deepCopy(); current.put("id", ACTOR); current.put("username", "operator");
        when(gateway.user(ACTOR)).thenReturn(current);
        when(gateway.effectiveRoles(ACTOR)).thenReturn(List.of(IMPLEMENTATOR));
        when(gateway.user(TARGET)).thenReturn(target);
        when(gateway.directRoles(TARGET)).thenReturn(List.of(USER, OTHER));
        when(gateway.effectiveRoles(TARGET)).thenReturn(List.of(USER, OTHER));
        when(gateway.role("ADMIN")).thenReturn(ADMIN);
        when(gateway.role("USER")).thenReturn(USER);
        when(gateway.role("IMPLEMENTATOR")).thenReturn(IMPLEMENTATOR);
    }

    @Test void tokenRolesAndScopeAreRequiredBeforeAnyUpstreamOperation() {
        for (Actor denied : List.of(new Actor(ACTOR, "admin", "IT", Set.of("ADMIN"), Set.of("members:manage")),
                new Actor(ACTOR, "operator", "IT", Set.of("IMPLEMENTATOR"), Set.of("documents:read")))) {
            assertThrows(AccessDeniedException.class, () -> service.list(denied, "", 0));
        }
        verifyNoInteractions(gateway);
    }

    @Test void staleTokenCannotRetainRevokedOrDisabledImplementatorPrivilege() {
        when(gateway.effectiveRoles(ACTOR)).thenReturn(List.of(USER));
        assertThrows(AccessDeniedException.class, () -> service.list(actor, "", 0));
        verify(gateway, never()).users(anyString(), anyInt(), anyInt());
        when(gateway.effectiveRoles(ACTOR)).thenReturn(List.of(IMPLEMENTATOR));
        when(gateway.user(ACTOR)).thenReturn(target.deepCopy().put("enabled", false));
        assertThrows(AccessDeniedException.class, () -> service.update(actor, TARGET, access("USER")));
        verify(gateway, never()).updateUser(eq(TARGET), any());
    }

    @Test void paginationIsBoundedAndServiceAccountsAreExcluded() {
        ObjectNode robot = target.deepCopy().put("username", "service-account-robot");
        when(gateway.users("member", 40, 21)).thenReturn(List.of(target, robot));
        var result = service.list(actor, " member ", 2);
        assertEquals(2, result.page()); assertFalse(result.hasMore());
        assertEquals(1, result.members().size());
        assertEquals(List.of("USER"), result.members().get(0).roles());
        assertEquals("HR", result.members().get(0).department());
        for (int page : List.of(-1, 10001)) assertStatus(400, () -> service.list(actor, "", page));
        assertStatus(400, () -> service.list(actor, "x".repeat(81), 0));
    }

    @Test void selfAccessAndServiceAccountsCannotBeChanged() {
        assertThrows(AccessDeniedException.class, () -> service.update(actor, ACTOR, access("ADMIN")));
        when(gateway.user(TARGET)).thenReturn(target.deepCopy().put("serviceAccountClientId", "robot"));
        assertThrows(AccessDeniedException.class, () -> service.update(actor, TARGET, access("ADMIN")));
        verify(gateway, never()).addRoles(anyString(), anyList());
        verify(gateway, never()).removeRoles(anyString(), anyList());
    }

    @Test void onlyWhitelistedRolesDepartmentsAndCanonicalIdsAreAccepted() {
        for (var request : List.of(access("realm-admin"), access("USER", "USER"),
                new MemberManagementService.Access(List.of(), "IT"),
                new MemberManagementService.Access(List.of("ADMIN"), "EXECUTIVE"))) {
            assertStatus(400, () -> service.update(actor, TARGET, request));
        }
        for (String id : List.of("../roles", "1-1-1-1-1", TARGET + "/credentials")) {
            assertStatus(400, () -> service.update(actor, id, access("ADMIN")));
        }
        verify(gateway, never()).directRoles(anyString());
    }

    @Test void updatePreservesOtherRolesAndAllExistingProfileFields() {
        ObjectNode after = target.deepCopy(); after.withObject("/attributes").putArray("department").add("IT");
        when(gateway.user(TARGET)).thenReturn(target, after);
        when(gateway.effectiveRoles(TARGET)).thenReturn(List.of(USER, OTHER), List.of(ADMIN, IMPLEMENTATOR, OTHER));
        service.update(actor, TARGET, access("ADMIN", "IMPLEMENTATOR"));
        verify(gateway).removeRoles(TARGET, List.of(USER));
        verify(gateway).addRoles(TARGET, List.of(ADMIN, IMPLEMENTATOR));
        var payload = ArgumentCaptor.forClass(ObjectNode.class);
        verify(gateway).updateUser(eq(TARGET), payload.capture());
        ObjectNode expected = target.deepCopy(); expected.withObject("/attributes").putArray("department").add("IT");
        assertEquals(expected, payload.getValue());
        assertEquals("original", payload.getValue().path("attributes").path("retained").get(0).asText());
        assertEquals("VERIFY_EMAIL", payload.getValue().path("requiredActions").get(0).asText());
        assertEquals("HR", target.path("attributes").path("department").get(0).asText());
        verify(gateway, never()).removeRoles(TARGET, List.of(OTHER));
    }

    @Test void inheritedManagedRolesAreNotFalselyReportedAsRemoved() {
        when(gateway.effectiveRoles(TARGET)).thenReturn(List.of(USER, ADMIN));
        assertStatus(409, () -> service.update(actor, TARGET, access("USER")));
        verify(gateway, never()).updateUser(anyString(), any());
    }

    @Test void overlappingDirectAndInheritedRoleCannotProduceFalseSuccess() {
        when(gateway.directRoles(TARGET)).thenReturn(List.of(USER, ADMIN), List.of(USER));
        when(gateway.effectiveRoles(TARGET)).thenReturn(List.of(USER, ADMIN));
        ObjectNode after = target.deepCopy(); after.withObject("/attributes").putArray("department").add("IT");
        when(gateway.user(TARGET)).thenReturn(target, after);
        assertStatus(409, () -> service.update(actor, TARGET, access("USER")));
        verify(gateway).addRoles(TARGET, List.of(ADMIN));
        verify(gateway).updateUser(TARGET, target);
    }

    @Test void partialUpstreamFailureRestoresManagedRolesAndOriginalProfile() {
        when(gateway.directRoles(TARGET)).thenReturn(List.of(USER, OTHER), List.of(ADMIN, OTHER));
        doThrow(KeycloakMembersClient.unavailable()).doNothing().when(gateway).updateUser(eq(TARGET), any());
        assertStatus(503, () -> service.update(actor, TARGET, access("ADMIN")));
        verify(gateway).removeRoles(TARGET, List.of(ADMIN));
        verify(gateway).addRoles(TARGET, List.of(USER));
        verify(gateway).updateUser(TARGET, target);
    }

    private static MemberManagementService.Access access(String... roles) {
        return new MemberManagementService.Access(List.of(roles), "IT");
    }

    private static void assertStatus(int status, Runnable action) {
        assertEquals(status, assertThrows(ResponseStatusException.class, action::run).getStatusCode().value());
    }
}
