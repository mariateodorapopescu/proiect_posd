package ro.securesync.api.common;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.*;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.support.MissingServletRequestPartException;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.util.Map;
import org.springframework.http.converter.HttpMessageNotReadableException;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(ResponseStatusException.class)
    ResponseEntity<?> status(ResponseStatusException exception) {
        return ResponseEntity.status(exception.getStatusCode()).body(Map.of("message",
                exception.getReason() == null ? "Request failed" : exception.getReason()));
    }

    @ExceptionHandler(AccessDeniedException.class)
    ResponseEntity<?> denied() {
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body(Map.of("message", "Acces refuzat de politica de autorizare."));
    }

    @ExceptionHandler({MissingServletRequestPartException.class, MissingServletRequestParameterException.class,
            MethodArgumentTypeMismatchException.class, HttpMessageNotReadableException.class})
    ResponseEntity<?> invalid() {
        return ResponseEntity.badRequest().body(Map.of("message", "Check the required request fields"));
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<?> tooLarge() {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE).body(Map.of("message", "Maximum PDF size is 10 MiB"));
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    ResponseEntity<?> conflict() {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of("message", "The document could not be saved"));
    }
}
