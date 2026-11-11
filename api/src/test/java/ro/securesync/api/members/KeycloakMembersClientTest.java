package ro.securesync.api.members;

import org.junit.jupiter.api.*;
import org.springframework.http.*;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class KeycloakMembersClientTest {
    private static final String BASE = "http://keycloak.test/admin/realms/securesync";
    private static final String TOKEN = "http://keycloak.test/realms/securesync/protocol/openid-connect/token";
    RestTemplate rest;
    MockRestServiceServer server;
    KeycloakMembersClient client;

    @BeforeEach void prepare() {
        rest = new RestTemplate();
        server = MockRestServiceServer.bindTo(rest).build();
        client = new KeycloakMembersClient(rest, BASE, TOKEN, "test-client", "synthetic-secret");
    }

    @Test void clientCredentialsStayInTokenRequestAndTokenIsCached() {
        token("first");
        for (int i = 0; i < 2; i++) server.expect(requestTo(BASE + "/users/user-id"))
                .andExpect(method(HttpMethod.GET)).andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer first"))
                .andRespond(withSuccess("{\"id\":\"user-id\",\"username\":\"member\"}", MediaType.APPLICATION_JSON));
        assertEquals("member", client.user("user-id").path("username").asText());
        assertEquals("member", client.user("user-id").path("username").asText());
        server.verify();
    }

    @Test void roleMutationUsesNonemptyExplicitIdNameArraysAndEmptyDeleteIsSkipped() {
        client.removeRoles("user-id", List.of());
        client.addRoles("user-id", List.of());
        token("admin");
        server.expect(requestTo(BASE + "/users/user-id/role-mappings/realm"))
                .andExpect(method(HttpMethod.DELETE)).andExpect(content().json("[{\"id\":\"role-id\",\"name\":\"ADMIN\"}]"))
                .andRespond(withNoContent());
        client.removeRoles("user-id", List.of(new KeycloakMembersGateway.Role("role-id", "ADMIN")));
        server.verify();
    }

    @Test void redirectResponsesCannotPretendToCompleteMutationsOrTokenAcquisition() {
        server.expect(requestTo(TOKEN)).andRespond(withStatus(HttpStatus.FOUND)
                .header(HttpHeaders.LOCATION, "https://untrusted.test/")
                .contentType(MediaType.APPLICATION_JSON).body("{\"access_token\":\"untrusted\",\"expires_in\":60}"));
        assertUnavailable(() -> client.user("user-id"));
        server.verify();

        prepare(); token("admin");
        server.expect(requestTo(BASE + "/users/user-id/role-mappings/realm"))
                .andRespond(withStatus(HttpStatus.FOUND).header(HttpHeaders.LOCATION, "https://untrusted.test/"));
        assertUnavailable(() -> client.addRoles("user-id", List.of(new KeycloakMembersGateway.Role("role", "ADMIN"))));
        server.verify();
    }

    @Test void unauthorizedServiceTokenIsRefreshedOnceAndUpstreamErrorsAreGeneric() {
        token("expired");
        server.expect(requestTo(BASE + "/users/user-id")).andRespond(withUnauthorizedRequest());
        token("fresh");
        server.expect(requestTo(BASE + "/users/user-id")).andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer fresh"))
                .andRespond(withStatus(HttpStatus.FORBIDDEN).contentType(MediaType.APPLICATION_JSON)
                        .body("{\"error\":\"internal provider credentials detail\"}"));
        ResponseStatusException failure = assertUnavailable(() -> client.user("user-id"));
        assertFalse(failure.getReason().contains("credentials"));
        server.verify();
    }

    @Test void missingUserIs404ButRoleConfigurationFailureIs503() {
        token("admin");
        server.expect(requestTo(BASE + "/users/gone")).andRespond(withResourceNotFound());
        server.expect(requestTo(BASE + "/roles/ADMIN")).andRespond(withResourceNotFound());
        assertEquals(404, assertThrows(ResponseStatusException.class, () -> client.user("gone")).getStatusCode().value());
        assertUnavailable(() -> client.role("ADMIN"));
        server.verify();
    }

    private void token(String value) {
        server.expect(requestTo(TOKEN)).andExpect(method(HttpMethod.POST))
                .andExpect(header(HttpHeaders.AUTHORIZATION, "Basic dGVzdC1jbGllbnQ6c3ludGhldGljLXNlY3JldA=="))
                .andExpect(content().string("grant_type=client_credentials"))
                .andRespond(withSuccess("{\"access_token\":\"" + value + "\",\"expires_in\":60}", MediaType.APPLICATION_JSON));
    }

    private static ResponseStatusException assertUnavailable(Runnable action) {
        ResponseStatusException failure = assertThrows(ResponseStatusException.class, action::run);
        assertEquals(503, failure.getStatusCode().value());
        return failure;
    }
}
