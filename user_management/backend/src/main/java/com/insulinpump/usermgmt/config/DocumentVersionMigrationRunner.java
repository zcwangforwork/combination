package com.insulinpump.usermgmt.config;

import com.insulinpump.usermgmt.model.Document;
import com.insulinpump.usermgmt.model.DocumentStatus;
import com.insulinpump.usermgmt.repository.DocumentRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 文档版本控制数据迁移 Runner
 *
 * 启动时自动将旧文档（status 为 null）迁移为版本化模型:
 *  - version = "v1.0"
 *  - status = PUBLISHED
 *  - effectiveDate = createdAt
 *
 * 此 Runner 幂等: 只处理 status=null 的文档，已迁移的不会重复处理。
 */
@Component
public class DocumentVersionMigrationRunner implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(DocumentVersionMigrationRunner.class);

    @Autowired
    private DocumentRepository documentRepository;

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        List<Document> oldDocs = documentRepository.findByStatusIsNull();
        if (oldDocs.isEmpty()) {
            return;
        }

        log.info("发现 {} 条旧文档需要迁移为版本化模型", oldDocs.size());

        for (Document doc : oldDocs) {
            doc.setVersion("v1.0");
            doc.setStatus(DocumentStatus.PUBLISHED);
            doc.setEffectiveDate(doc.getCreatedAt() != null ? doc.getCreatedAt() : LocalDateTime.now());
        }

        documentRepository.saveAll(oldDocs);
        log.info("文档版本化迁移完成，{} 条文档已设为 v1.0 PUBLISHED", oldDocs.size());
    }
}
