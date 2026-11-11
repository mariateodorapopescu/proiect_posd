package ro.securesync.api.members;

import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.List;

/** The only external operations exposed to member management. */
public interface KeycloakMembersGateway {
    record Role(String id, String name) { }
    List<ObjectNode> users(String search, int first, int max);
    ObjectNode user(String id);
    List<Role> directRoles(String id);
    List<Role> effectiveRoles(String id);
    Role role(String name);
    void addRoles(String id, List<Role> roles);
    void removeRoles(String id, List<Role> roles);
    void updateUser(String id, ObjectNode representation);
}
