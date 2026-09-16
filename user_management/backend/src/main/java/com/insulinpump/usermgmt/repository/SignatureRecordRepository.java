package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.SignatureRecord;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * 电子签名记录 Repository
 *
 * 同审计日志：只允许 INSERT + SELECT，不允许 UPDATE + DELETE。
 */
public interface SignatureRecordRepository extends JpaRepository<SignatureRecord, Long> {

    List<SignatureRecord> findByEntityIdOrderBySignedAtDesc(Long entityId);

    List<SignatureRecord> findByUserIdOrderBySignedAtDesc(Long userId);
}
