package ro.securesync.api.documents;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

class PdfStorageTest {
    @TempDir Path temporary;

    @Test void storesOnlyGeneratedNamesAndConstrainedPaths() throws Exception {
        PdfStorage storage = new PdfStorage(temporary.resolve("pdfs").toString());
        byte[] content = "%PDF-1.7\ntest".getBytes();
        var saved = storage.store(new MockMultipartFile("file", "../../outside.pdf", "application/pdf", content));
        assertTrue(saved.key().startsWith("doc_"));
        assertEquals(content.length, saved.size());
        assertArrayEquals(content, Files.readAllBytes(storage.existing(saved.key())));
        assertNull(storage.existing("../outside.pdf"));
        assertNull(storage.existing("..\\outside.pdf"));
        assertNull(storage.existing("/tmp/outside.pdf"));
        storage.delete("../outside.pdf");
        storage.delete(saved.key());
        assertNull(storage.existing(saved.key()));
    }

    @Test void rejectsOversizeAndInvalidBodiesWithoutResidualFiles() throws Exception {
        Path directory = Files.createDirectory(temporary.resolve("pdfs"));
        PdfStorage storage = new PdfStorage(directory.toString());
        byte[] oversize = new byte[(int) PdfStorage.MAX_SIZE + 1];
        System.arraycopy("%PDF-".getBytes(), 0, oversize, 0, 5);
        assertThrows(ResponseStatusException.class, () -> storage.store(
                new MockMultipartFile("file", "large.pdf", "application/pdf", oversize)));
        assertThrows(ResponseStatusException.class, () -> storage.store(
                new MockMultipartFile("file", "fake.pdf", "application/pdf", "fake".getBytes())));
        try (var files = Files.list(directory)) { assertEquals(0, files.count()); }
    }

    @Test void rejectsSymlinkFileAndRoot() throws Exception {
        Path directory = Files.createDirectory(temporary.resolve("pdfs"));
        Path outside = Files.writeString(temporary.resolve("outside.pdf"), "retain");
        String key = "doc_11111111-1111-1111-1111-111111111111.pdf";
        try { Files.createSymbolicLink(directory.resolve(key), outside); }
        catch (UnsupportedOperationException | IOException | SecurityException exception) {
            assumeTrue(false, "Filesystem does not permit test symlinks");
        }
        PdfStorage storage = new PdfStorage(directory.toString());
        assertNull(storage.existing(key));
        storage.delete(key);
        assertEquals("retain", Files.readString(outside));
        Path linkedRoot = Files.createSymbolicLink(temporary.resolve("linked"), directory);
        PdfStorage linked = new PdfStorage(linkedRoot.toString());
        assertThrows(IOException.class, () -> linked.existing(key));
        assertThrows(IOException.class, () -> linked.store(
                new MockMultipartFile("file", "valid.pdf", "application/pdf", "%PDF-1.7".getBytes())));
    }
}
