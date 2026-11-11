package ro.securesync.api.documents;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Arrays;
import java.util.UUID;
import java.util.regex.Pattern;

/** A private filesystem boundary. Client filenames never participate in filesystem paths. */
@Component
public class PdfStorage {
    public static final long MAX_SIZE = 10 * 1024 * 1024;
    private static final Pattern KEY = Pattern.compile("doc_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.pdf");
    private static final byte[] HEADER = "%PDF-".getBytes(StandardCharsets.US_ASCII);
    private final Path root;

    public PdfStorage(@Value("${app.storage-root}") String root) {
        this.root = Path.of(root).toAbsolutePath().normalize();
    }

    public record StoredPdf(String key, long size) { }

    public StoredPdf store(MultipartFile file) throws IOException {
        if (file == null || file.isEmpty()) throw invalid("Select a PDF file");
        if (file.getSize() > MAX_SIZE) throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE, "Maximum PDF size is 10 MiB");
        if (!"application/pdf".equalsIgnoreCase(file.getContentType())) throw invalid("Only application/pdf is accepted");
        try (InputStream input = file.getInputStream()) {
            byte[] header = input.readNBytes(HEADER.length);
            if (!Arrays.equals(HEADER, header)) throw invalid("The file must begin with a PDF header");
            Files.createDirectories(root);
            Path directory = realRoot();
            String key = "doc_" + UUID.randomUUID() + ".pdf";
            Path target = directory.resolve(key);
            boolean created = false;
            long size = header.length;
            try (var output = Files.newOutputStream(target, StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS)) {
                created = true;
                output.write(header);
                byte[] buffer = new byte[8192];
                int read;
                while ((read = input.read(buffer)) != -1) {
                    size += read;
                    if (size > MAX_SIZE) throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE, "Maximum PDF size is 10 MiB");
                    output.write(buffer, 0, read);
                }
            } catch (IOException | RuntimeException exception) {
                if (created) Files.deleteIfExists(target);
                throw exception;
            }
            return new StoredPdf(key, size);
        }
    }

    public Path existing(String key) throws IOException {
        if (key == null || !KEY.matcher(key).matches()) return null;
        if (!Files.exists(root, LinkOption.NOFOLLOW_LINKS)) return null;
        Path directory = realRoot();
        Path target = directory.resolve(key).normalize();
        if (!target.startsWith(directory) || !Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS)) return null;
        Path real = target.toRealPath();
        return real.equals(target) && real.startsWith(directory) ? real : null;
    }

    public void delete(String key) throws IOException {
        Path file = existing(key);
        if (file != null) Files.deleteIfExists(file);
    }

    private Path realRoot() throws IOException {
        Path real = root.toRealPath();
        if (!real.equals(root) || !Files.isDirectory(real, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Unsafe PDF storage directory");
        }
        return real;
    }

    private static ResponseStatusException invalid(String message) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
    }
}
