package ro.securesync.api.documents;

import jakarta.persistence.*;

import java.time.Instant;

@Entity
@Table(name = "documents")
public class Document {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(nullable = false, length = 160)
    private String title;
    @Column(nullable = false, length = 200)
    private String originalFilename;
    @Column(nullable = false, unique = true, length = 64)
    private String storageKey;
    @Column(nullable = false)
    private String ownerId;
    @Column(nullable = false, length = 100)
    private String department;
    @Column(name = "size_bytes", nullable = false)
    private long size;
    @Column(nullable = false)
    private Instant createdAt;

    protected Document() { }

    public Document(String title, String originalFilename, String storageKey, String ownerId,
                    String department, long size) {
        this.title = title;
        this.originalFilename = originalFilename;
        this.storageKey = storageKey;
        this.ownerId = ownerId;
        this.department = department;
        this.size = size;
        this.createdAt = Instant.now();
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public String getOriginalFilename() { return originalFilename; }
    public String getStorageKey() { return storageKey; }
    public String getOwnerId() { return ownerId; }
    public String getDepartment() { return department; }
    public long getSize() { return size; }
    public Instant getCreatedAt() { return createdAt; }
}
