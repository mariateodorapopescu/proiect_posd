package ro.securesync.api.members;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import ro.securesync.api.security.Actor;

@RestController
@RequestMapping("/api/members")
@PreAuthorize("hasAuthority('SCOPE_members:manage') and hasRole('IMPLEMENTATOR')")
public class MembersController {
    private final MemberManagementService service;
    public MembersController(MemberManagementService service) { this.service = service; }

    @GetMapping
    public MemberManagementService.Page list(Authentication authentication,
            @RequestParam(defaultValue = "") String search, @RequestParam(defaultValue = "0") int page) {
        return service.list(Actor.from(authentication), search, page);
    }

    @PutMapping("/{id}/access")
    public MemberManagementService.Member update(Authentication authentication, @PathVariable String id,
            @RequestBody MemberManagementService.Access request) {
        return service.update(Actor.from(authentication), id, request);
    }
}
