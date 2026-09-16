package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.config.RequestContextFilter;
import com.insulinpump.usermgmt.model.SignatureRecord;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.repository.SignatureRecordRepository;
import com.insulinpump.usermgmt.util.ChecksumUtil;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

/**
 * 电子签名 Service
 *
 * FDA 21 CFR Part 11 合规：电子签名需签名者身份 + 签名时间 + 签名含义。
 *
 * 流程：
 *  1. 校验密码（passwordEncoder.matches）
 *  2. 计算签名哈希 SHA-256(userId|username|realName|action|entityType|entityId|meaning|signedAt|passwordHash)
 *  3. 保存签名记录到 t_signature_record
 *  4. 通过 RequestContextFilter.setSignatureId() 关联到审计日志
 *
 * 事务边界（用户决策 #6）：
 *  本方法在 DocumentService 的 @Transactional 方法内部调用，
 *  签名与业务在同一事务，业务失败则签名一起回滚。
 */
@Service
public class SignatureService {

    private final PasswordEncoder passwordEncoder;
    private final SignatureRecordRepository signatureRepository;

    public SignatureService(PasswordEncoder passwordEncoder,
                            SignatureRecordRepository signatureRepository) {
        this.passwordEncoder = passwordEncoder;
        this.signatureRepository = signatureRepository;
    }

    /**
     * 校验密码 + 记录签名
     *
     * @param user      签名用户（从 SecurityContext 获取）
     * @param password  用户输入的明文密码
     * @param action    签名动作 (PUBLISH/APPROVE/REJECT/RETIRE/ROLLBACK)
     * @param entityType 实体类型 (DOCUMENT)
     * @param entityId  实体 ID
     * @param meaning   签名含义（如"我批准此文档版本发布生效"）
     * @return 签名记录
     * @throws BadCredentialsException 密码错误
     * @throws IllegalArgumentException 密码或含义为空
     */
    public SignatureRecord verifyAndRecord(User user, String password,
                                            String action, String entityType,
                                            Long entityId, String meaning) {
        // 1. 参数校验
        if (user == null) {
            throw new IllegalArgumentException("签名需要登录用户");
        }
        if (password == null || password.isBlank()) {
            throw new IllegalArgumentException("签名需要输入密码");
        }
        if (meaning == null || meaning.isBlank()) {
            throw new IllegalArgumentException("签名需要填写签名含义");
        }

        // 2. 密码校验
        if (!passwordEncoder.matches(password, user.getPassword())) {
            throw new BadCredentialsException("签名密码错误");
        }

        // 3. 计算签名哈希
        String signedAt = String.valueOf(System.currentTimeMillis());
        String signatureHash = ChecksumUtil.sha256(
                user.getId() + "|" +
                user.getUsername() + "|" +
                user.getRealName() + "|" +
                action + "|" +
                entityType + "|" +
                entityId + "|" +
                meaning + "|" +
                signedAt + "|" +
                user.getPassword()
        );

        // 4. 保存签名记录
        SignatureRecord sig = new SignatureRecord();
        sig.setUserId(user.getId());
        sig.setUsername(user.getUsername());
        sig.setRealName(user.getRealName());
        sig.setAction(action);
        sig.setEntityType(entityType);
        sig.setEntityId(entityId);
        sig.setMeaning(meaning);
        sig.setSignatureHash(signatureHash);
        sig.setPasswordHashSnapshot(user.getPassword());

        RequestContextFilter.RequestContext ctx = RequestContextFilter.getContext();
        sig.setIp(ctx.getIp());
        sig.setUserAgent(ctx.getUserAgent());

        SignatureRecord saved = signatureRepository.save(sig);

        // 5. 关联到审计日志
        RequestContextFilter.setSignatureId(saved.getId());

        return saved;
    }
}
