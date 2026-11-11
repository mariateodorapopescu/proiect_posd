package ro.securesync.api.common;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import ro.securesync.api.security.Actor;

import java.util.Map;
import java.util.Set;

@RestController
@RequestMapping("/api")
public class SystemController {
    private final String strategy;
    public SystemController(@Value("${app.token-strategy:jwt}") String strategy) { this.strategy = strategy; }

    @GetMapping("/health")
    public Map<String, String> health() { return Map.of("status", "UP", "strategy", strategy); }

    public record MeResponse(String sub, String username, String department, Set<String> roles,
                             Set<String> scopes, String strategy) { }

    @GetMapping("/me")
    public MeResponse me(Authentication authentication) {
        Actor actor = Actor.from(authentication);
        return new MeResponse(actor.sub(), actor.username(), actor.department(), actor.roles(), actor.scopes(), strategy);
    }
}
