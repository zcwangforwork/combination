package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.DocumentFile;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.transaction.annotation.Transactional;

import java.util.Optional;

public interface DocumentFileRepository extends JpaRepository<DocumentFile, Long> {

    Optional<DocumentFile> findByDocumentId(Long documentId);

    @Transactional
    void deleteByDocumentId(Long documentId);
}
