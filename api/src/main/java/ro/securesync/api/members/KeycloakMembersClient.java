package ro.securesync.api.members;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.*;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.util.UriComponentsBuilder;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/** Server-only client credentials; no admin credential is sent to the browser. */
@Component
public class KeycloakMembersClient implements KeycloakMembersGateway {
    private final RestTemplate http;
    private final String baseUrl;
    private final String tokenUrl;
    private final String clientId;
    private final String secret;
    private String token;
    private Instant tokenExpires = Instant.EPOCH;

    @Autowired
    public KeycloakMembersClient(@Value("${app.members.base-url}") String baseUrl,
            @Value("${app.members.token-url}") String tokenUrl,
            @Value("${app.members.client-id}") String clientId,
            @Value("${app.members.client-secret}") String secret) {
        this(template(), baseUrl, tokenUrl, clientId, secret);
    }

    KeycloakMembersClient(RestTemplate http, String baseUrl, String tokenUrl, String clientId, String secret) {
        this.http = http;
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.tokenUrl = tokenUrl;
        this.clientId = clientId;
        this.secret = secret;
    }

    private static RestTemplate template() {
        var factory = new JdkClientHttpRequestFactory(HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3)).followRedirects(HttpClient.Redirect.NEVER).build());
        factory.setReadTimeout(Duration.ofSeconds(3));
        return new RestTemplate(factory);
    }

    @Override public List<ObjectNode> users(String search, int first, int max) {
        URI uri = UriComponentsBuilder.fromUriString(baseUrl + "/users")
                .queryParam("search", search).queryParam("first", first).queryParam("max", max)
                .queryParam("briefRepresentation", false).build().encode().toUri();
        JsonNode body = exchange(uri, HttpMethod.GET, null, false);
        if (body == null || !body.isArray() || body.size() > max) throw unavailable();
        List<ObjectNode> users = new ArrayList<>();
        for (JsonNode user : body) {
            if (!(user instanceof ObjectNode object)) throw unavailable();
            users.add(object);
        }
        return users;
    }

    @Override public ObjectNode user(String id) {
        JsonNode body = exchange(uri("users", id), HttpMethod.GET, null, true);
        if (!(body instanceof ObjectNode object)) throw unavailable();
        return object;
    }

    @Override public List<Role> directRoles(String id) { return roles(uri("users", id, "role-mappings", "realm")); }
    @Override public List<Role> effectiveRoles(String id) { return roles(uri("users", id, "role-mappings", "realm", "composite")); }

    @Override public Role role(String name) {
        JsonNode body = exchange(uri("roles", name), HttpMethod.GET, null, false);
        return asRole(body);
    }

    private List<Role> roles(URI uri) {
        JsonNode body = exchange(uri, HttpMethod.GET, null, false);
        if (body == null || !body.isArray()) throw unavailable();
        List<Role> roles = new ArrayList<>();
        for (JsonNode item : body) roles.add(asRole(item));
        return roles;
    }

    private Role asRole(JsonNode body) {
        if (body == null || !body.path("id").isTextual() || !body.path("name").isTextual()
                || body.path("id").asText().isBlank() || body.path("name").asText().isBlank()) throw unavailable();
        return new Role(body.path("id").asText(), body.path("name").asText());
    }

    @Override public void addRoles(String id, List<Role> roles) {
        if (!roles.isEmpty()) exchange(uri("users", id, "role-mappings", "realm"), HttpMethod.POST, roles, false);
    }

    @Override public void removeRoles(String id, List<Role> roles) {
        // Keycloak interprets a null DELETE body as deleting every direct realm role.
        if (!roles.isEmpty()) exchange(uri("users", id, "role-mappings", "realm"), HttpMethod.DELETE, roles, false);
    }

    @Override public void updateUser(String id, ObjectNode representation) {
        exchange(uri("users", id), HttpMethod.PUT, representation, false);
    }

    private URI uri(String... segments) {
        return UriComponentsBuilder.fromUriString(baseUrl).pathSegment(segments).build().encode().toUri();
    }

    private JsonNode exchange(URI uri, HttpMethod method, Object body, boolean missingUser) {
        for (int attempt = 0; attempt < 2; attempt++) {
            HttpHeaders headers = new HttpHeaders();
            headers.setBearerAuth(accessToken());
            headers.setContentType(MediaType.APPLICATION_JSON);
            try {
                ResponseEntity<JsonNode> response = http.exchange(uri, method, new HttpEntity<>(body, headers), JsonNode.class);
                int expected = method == HttpMethod.GET ? 200 : 204;
                if (response.getStatusCode().value() != expected) throw unavailable();
                return response.getBody();
            } catch (HttpClientErrorException exception) {
                if (exception.getStatusCode().value() == 401 && attempt == 0) { invalidateToken(); continue; }
                if (exception.getStatusCode().value() == 404 && missingUser) {
                    throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Membrul nu mai exista.");
                }
                throw unavailable();
            } catch (RestClientException exception) { throw unavailable(); }
        }
        throw unavailable();
    }

    private synchronized String accessToken() {
        if (token != null && Instant.now().isBefore(tokenExpires)) return token;
        if (secret == null || secret.isBlank() || clientId.isBlank()) throw unavailable();
        HttpHeaders headers = new HttpHeaders();
        headers.setBasicAuth(clientId, secret);
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);
        var form = new LinkedMultiValueMap<String, String>();
        form.add("grant_type", "client_credentials");
        try {
            ResponseEntity<JsonNode> response = http.postForEntity(tokenUrl, new HttpEntity<>(form, headers), JsonNode.class);
            if (response.getStatusCode().value() != 200) throw unavailable();
            JsonNode body = response.getBody();
            if (body == null || !body.path("access_token").isTextual() || body.path("access_token").asText().isBlank()
                    || !body.path("expires_in").canConvertToLong() || body.path("expires_in").asLong() < 1) throw unavailable();
            token = body.path("access_token").asText();
            tokenExpires = Instant.now().plusSeconds(Math.max(0, body.path("expires_in").asLong() - 5));
            return token;
        } catch (RestClientException exception) { throw unavailable(); }
    }

    private synchronized void invalidateToken() { token = null; tokenExpires = Instant.EPOCH; }

    static ResponseStatusException unavailable() {
        return new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                "Administrarea membrilor nu este disponibila momentan. Reincarca lista inainte de a reincerca.");
    }
}
