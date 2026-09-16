package com.insulinpump.usermgmt.audit;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.insulinpump.usermgmt.config.RequestContextFilter;
import com.insulinpump.usermgmt.config.RequestContextFilter.RequestContext;
import com.insulinpump.usermgmt.model.AuditLog;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.repository.AuditLogRepository;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

/**
 * 审计日志 AOP 切面
 *
 * 拦截所有标注 @Auditable 的方法，自动记录审计日志。
 *
 * 审计写入失败不阻断业务（用户决策 #2）：
 *   - 业务方法正常执行
 *   - 审计写入失败时记录到 stderr/应用日志
 *   - 业务结果不受影响
 *
 * before 状态来源（用户决策 #3）：
 *   Service 层在方法内调用 RequestContextFilter.setAuditBefore(json) 提供
 */
@Aspect
@Component
public class AuditAspect {

    private static final Logger log = LoggerFactory.getLogger(AuditAspect.class);

    private final AuditLogRepository auditLogRepository;
    private final ObjectMapper objectMapper;

    public AuditAspect(AuditLogRepository auditLogRepository) {
        this.auditLogRepository = auditLogRepository;
        this.objectMapper = new ObjectMapper();
        this.objectMapper.configure(SerializationFeature.FAIL_ON_EMPTY_BEANS, false);
    }

    @Around("@annotation(auditable)")
    public Object audit(ProceedingJoinPoint pjp, Auditable auditable) throws Throwable {
        User user = getCurrentUser();
        Object result = null;
        String errorMsg = null;
        boolean success = true;

        try {
            result = pjp.proceed();
            return result;
        } catch (Throwable e) {
            success = false;
            errorMsg = e.getMessage();
            throw e;  // 重新抛出，不影响原逻辑
        } finally {
            writeAuditLog(pjp, auditable, user, result, success, errorMsg);
        }
    }

    private void writeAuditLog(ProceedingJoinPoint pjp, Auditable auditable,
                                User user, Object result, boolean success, String errorMsg) {
        try {
            AuditLog auditLog = new AuditLog();
            auditLog.setUserId(user != null ? user.getId() : null);
            auditLog.setUsername(user != null ? user.getUsername() : "ANONYMOUS");
            auditLog.setAction(auditable.action());
            auditLog.setEntityType(auditable.entityType());
            auditLog.setEntityId(extractEntityId(pjp.getArgs()));
            auditLog.setResult(success ? "SUCCESS" : "FAILURE");
            auditLog.setErrorMsg(truncate(errorMsg, 1000));

            RequestContext ctx = RequestContextFilter.getContext();
            auditLog.setIp(ctx.getIp());
            auditLog.setUserAgent(truncate(ctx.getUserAgent(), 500));

            // before: Service 层通过 RequestContextFilter.setAuditBefore() 设置
            String beforeJson = ctx.getAuditBefore();
            if (beforeJson != null) {
                auditLog.setBeforeJson(beforeJson);
            }

            // after: 方法返回值序列化（仅成功时）
            if (success && result != null) {
                auditLog.setAfterJson(serializeSafely(result));
            }

            // 签名 ID: Service 层通过 RequestContextFilter.setSignatureId() 设置
            Long signatureId = ctx.getSignatureId();
            if (signatureId != null) {
                auditLog.setSignatureId(signatureId);
            }

            auditLogRepository.save(auditLog);
        } catch (Exception logEx) {
            // 审计写入失败不阻断业务（用户决策 #2）
            log.error("审计日志写入失败 action={} entityType={}",
                    auditable.action(), auditable.entityType(), logEx);
        } finally {
            // 清除审计上下文，避免线程复用污染
            RequestContextFilter.clearAuditContext();
        }
    }

    private User getCurrentUser() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.getPrincipal() instanceof User) {
            return (User) auth.getPrincipal();
        }
        return null;
    }

    /**
     * 从方法参数提取实体 ID
     * 约定：第一个 Long 类型的参数视为 entityId
     */
    private Long extractEntityId(Object[] args) {
        if (args == null) return null;
        for (Object arg : args) {
            if (arg instanceof Long) {
                return (Long) arg;
            }
        }
        return null;
    }

    private String serializeSafely(Object obj) {
        try {
            String json = objectMapper.writeValueAsString(obj);
            return truncate(json, 10000);  // 限制 10KB 避免过大
        } catch (Exception e) {
            return "[serialization failed: " + e.getMessage() + "]";
        }
    }

    private String truncate(String s, int maxLen) {
        if (s == null) return null;
        return s.length() > maxLen ? s.substring(0, maxLen) : s;
    }
}
