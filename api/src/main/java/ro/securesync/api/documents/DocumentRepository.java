package ro.securesync.api.documents;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface DocumentRepository extends JpaRepository<Document, Long> {
    List<Document> findAllByOrderByCreatedAtDesc();

    @Query("select d from Document d where d.ownerId = :owner or (:department <> '' and d.department = :department) order by d.createdAt desc")
    List<Document> findVisible(@Param("owner") String owner, @Param("department") String department);
}
