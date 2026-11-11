package ro.securesync.api.documents;

import java.time.Instant;

public record DocumentResponse(Long id, String title, String originalFilename, String ownerId,
                               String department, long size, Instant createdAt) {
    public static DocumentResponse from(Document document) {
        return new DocumentResponse(document.getId(), document.getTitle(), document.getOriginalFilename(),
                document.getOwnerId(), document.getDepartment(), document.getSize(), document.getCreatedAt());
    }
}
