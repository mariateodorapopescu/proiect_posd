package ro.securesync.api.documents;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Component;
import ro.securesync.api.security.Actor;

@Component
public class DocumentPolicy {
    public boolean canRead(Actor actor, Document document) {
        return actor.admin() || document.getOwnerId().equals(actor.sub())
                || (!actor.department().isBlank() && actor.department().equals(document.getDepartment()));
    }

    public boolean canDelete(Actor actor, Document document) {
        return actor.admin() || document.getOwnerId().equals(actor.sub());
    }

    public void requireRead(Actor actor, Document document) {
        if (!canRead(actor, document)) throw new AccessDeniedException("Document access denied");
    }

    public void requireDelete(Actor actor, Document document) {
        if (!canDelete(actor, document)) throw new AccessDeniedException("Only the owner or an administrator may delete this document");
    }
}
