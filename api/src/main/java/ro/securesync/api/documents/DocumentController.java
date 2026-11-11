package ro.securesync.api.documents;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.*;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import ro.securesync.api.security.Actor;

import java.nio.charset.StandardCharsets;
import java.util.List;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {
    private final DocumentService service;
    public DocumentController(DocumentService service) { this.service = service; }

    @GetMapping
    @PreAuthorize("hasAuthority('SCOPE_documents:read') and hasAnyRole('USER', 'ADMIN')")
    public List<DocumentResponse> list(Authentication authentication) {
        return service.list(Actor.from(authentication));
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @PreAuthorize("hasAuthority('SCOPE_documents:write') and hasAnyRole('USER', 'ADMIN')")
    public DocumentResponse upload(Authentication authentication, @RequestParam String title,
                                   @RequestParam MultipartFile file) {
        return service.upload(Actor.from(authentication), title, file);
    }

    @GetMapping("/{id}/download")
    @PreAuthorize("hasAuthority('SCOPE_documents:read') and hasAnyRole('USER', 'ADMIN')")
    public ResponseEntity<Resource> download(Authentication authentication, @PathVariable long id) {
        var download = service.download(Actor.from(authentication), id);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .cacheControl(CacheControl.noStore())
                .header(HttpHeaders.CONTENT_DISPOSITION, ContentDisposition.attachment()
                        .filename(download.document().originalFilename(), StandardCharsets.UTF_8).build().toString())
                .header("X-Content-Type-Options", "nosniff")
                .body(new FileSystemResource(download.path()));
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('SCOPE_documents:write') and hasAnyRole('USER', 'ADMIN')")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(Authentication authentication, @PathVariable long id) {
        service.delete(Actor.from(authentication), id);
    }
}
