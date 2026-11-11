package ro.securesync.api.documents;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;
import ro.securesync.api.security.Actor;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;

@Service
public class DocumentService {
    private static final Logger log = LoggerFactory.getLogger(DocumentService.class);
    private final DocumentRepository repository;
    private final PdfStorage storage;
    private final DocumentPolicy policy;

    public DocumentService(DocumentRepository repository, PdfStorage storage, DocumentPolicy policy) {
        this.repository = repository;
        this.storage = storage;
        this.policy = policy;
    }

    @Transactional(readOnly = true)
    public List<DocumentResponse> list(Actor actor) {
        List<Document> documents = actor.admin() ? repository.findAllByOrderByCreatedAtDesc()
                : repository.findVisible(actor.sub(), actor.department());
        return documents.stream().map(DocumentResponse::from).toList();
    }

    @Transactional
    public DocumentResponse upload(Actor actor, String title, MultipartFile file) {
        if (title == null || title.isBlank() || title.strip().length() > 160) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Title is required and must have at most 160 characters");
        }
        if (actor.department().isBlank() || actor.department().length() > 100) {
            throw new AccessDeniedException("A valid department attribute is required for upload");
        }
        PdfStorage.StoredPdf stored;
        try { stored = storage.store(file); }
        catch (IOException exception) { throw unavailable(exception); }
        // If the database commit fails after this method returns, remove the newly written file.
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override public void afterCompletion(int status) {
                    if (status != STATUS_COMMITTED) cleanup(stored.key());
                }
            });
        }
        try {
            Document document = new Document(title.strip(), displayName(file.getOriginalFilename()), stored.key(),
                    actor.sub(), actor.department(), stored.size());
            return DocumentResponse.from(repository.saveAndFlush(document));
        } catch (RuntimeException exception) {
            cleanup(stored.key());
            throw exception;
        }
    }

    public record Download(DocumentResponse document, Path path) { }

    @Transactional(readOnly = true)
    public Download download(Actor actor, long id) {
        Document document = find(id);
        policy.requireRead(actor, document);
        try {
            Path path = storage.existing(document.getStorageKey());
            if (path == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "PDF file is unavailable");
            return new Download(DocumentResponse.from(document), path);
        } catch (IOException exception) { throw unavailable(exception); }
    }

    @Transactional
    public void delete(Actor actor, long id) {
        Document document = find(id);
        policy.requireDelete(actor, document);
        repository.delete(document);
        repository.flush();
        // Keep the file if the database rolls back; do not break the record before a successful commit.
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCommit() { cleanup(document.getStorageKey()); }
        });
    }

    private Document find(long id) {
        return repository.findById(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Document not found"));
    }

    private void cleanup(String key) {
        try { storage.delete(key); }
        catch (IOException exception) { log.warn("Could not clean up a private PDF file", exception); }
    }

    private ResponseStatusException unavailable(IOException cause) {
        return new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "PDF storage is unavailable", cause);
    }

    private static String displayName(String original) {
        if (original == null || original.isBlank()) return "document.pdf";
        String name = original.replace('\\', '/');
        name = name.substring(name.lastIndexOf('/') + 1).replaceAll("[\\p{Cntrl}]", "_").strip();
        if (name.isBlank()) return "document.pdf";
        return name.substring(0, Math.min(200, name.length()));
    }
}
