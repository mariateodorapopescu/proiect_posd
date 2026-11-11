package ro.securesync.api.documents;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.transaction.support.*;
import ro.securesync.api.security.Actor;

import java.nio.file.*;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class DocumentRollbackTest {
    @TempDir Path temporary;
    private static final Actor OWNER = new Actor("user-id", "user", "IT", Set.of("USER"), Set.of("documents:write"));

    @Test void databaseSaveFailureRemovesUploadedFile() throws Exception {
        DocumentRepository repository = mock(DocumentRepository.class);
        PdfStorage storage = new PdfStorage(temporary.toString());
        when(repository.saveAndFlush(any())).thenThrow(new DataIntegrityViolationException("synthetic test failure"));
        var service = new DocumentService(repository, storage, new DocumentPolicy());
        assertThrows(DataIntegrityViolationException.class, () -> service.upload(OWNER, "Policy", pdf()));
        try (var files = Files.list(temporary)) { assertEquals(0, files.count()); }
    }

    @Test void commitRollbackAfterMethodReturnRemovesUploadedFile() throws Exception {
        DocumentRepository repository = mock(DocumentRepository.class);
        PdfStorage storage = new PdfStorage(temporary.toString());
        when(repository.saveAndFlush(any())).thenAnswer(call -> call.getArgument(0));
        var service = new DocumentService(repository, storage, new DocumentPolicy());
        TransactionSynchronizationManager.initSynchronization();
        try {
            service.upload(OWNER, "Policy", pdf());
            try (var files = Files.list(temporary)) { assertEquals(1, files.count()); }
            TransactionSynchronizationManager.getSynchronizations().forEach(s -> s.afterCompletion(TransactionSynchronization.STATUS_ROLLED_BACK));
            try (var files = Files.list(temporary)) { assertEquals(0, files.count()); }
        } finally { TransactionSynchronizationManager.clearSynchronization(); }
    }

    private static MockMultipartFile pdf() {
        return new MockMultipartFile("file", "policy.pdf", "application/pdf", "%PDF-1.7\n%%EOF".getBytes());
    }
}
