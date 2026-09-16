package com.insulinpump.usermgmt.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 标记需要审计日志的方法
 *
 * 标注在 Service 层的外部入口方法上（Controller 调用的方法）。
 * AuditAspect 会拦截并记录：
 *  - 操作人（SecurityContext 中的 User）
 *  - 操作类型（action）
 *  - 实体类型（entityType）
 *  - 实体 ID（从方法参数提取）
 *  - 变更前状态（Service 层通过 RequestContextFilter.setAuditBefore() 提供）
 *  - 变更后状态（方法返回值序列化）
 *  - 操作结果（SUCCESS / FAILURE）
 *  - IP + UserAgent（从 RequestContextFilter 获取）
 *
 * 注意：Spring AOP 基于代理，不拦截类内部自调用。
 * 请只标注在 Controller 直接调用的 Service 方法上。
 *
 * 用法：
 *   @Auditable(action = "PUBLISH", entityType = "DOCUMENT")
 *   public DocumentDetailDto publish(Long id, String changeLog, User user) { ... }
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Auditable {
    /** 操作类型，如 PUBLISH / APPROVE / REJECT / RETIRE / ROLLBACK / UPLOAD / UPDATE / DELETE */
    String action();

    /** 实体类型，如 DOCUMENT / EMPLOYEE / RESEARCH_DATA */
    String entityType();
}
