package com.insulinpump.usermgmt.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * 请求上下文 Filter
 *
 * 捕获每个 HTTP 请求的 IP 和 User-Agent，存入 ThreadLocal。
 * AuditAspect 和 SignatureService 从中读取，写入审计日志/签名记录。
 *
 * IP 提取优先级：X-Forwarded-For > X-Real-IP > remoteAddr
 * （支持反向代理场景）
 */
@Component("requestContextHolderFilter")
public class RequestContextFilter extends OncePerRequestFilter {

    private static final ThreadLocal<RequestContext> CONTEXT_HOLDER = new ThreadLocal<>();

    public static RequestContext getContext() {
        RequestContext ctx = CONTEXT_HOLDER.get();
        return ctx != null ? ctx : new RequestContext(null, null);
    }

    /** Service 层可通过此方法设置 before 状态，供 AuditAspect 读取 */
    public static void setAuditBefore(String beforeJson) {
        RequestContext ctx = CONTEXT_HOLDER.get();
        if (ctx != null) {
            ctx.setAuditBefore(beforeJson);
        }
    }

    /** Service 层可通过此方法设置关联的签名 ID */
    public static void setSignatureId(Long signatureId) {
        RequestContext ctx = CONTEXT_HOLDER.get();
        if (ctx != null) {
            ctx.setSignatureId(signatureId);
        }
    }

    /** 清除审计上下文（方法执行完后清理，避免线程复用污染） */
    public static void clearAuditContext() {
        RequestContext ctx = CONTEXT_HOLDER.get();
        if (ctx != null) {
            ctx.setAuditBefore(null);
            ctx.setSignatureId(null);
        }
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String ip = extractIp(request);
        String userAgent = request.getHeader("User-Agent");
        RequestContext ctx = new RequestContext(ip, userAgent);
        CONTEXT_HOLDER.set(ctx);
        try {
            filterChain.doFilter(request, response);
        } finally {
            CONTEXT_HOLDER.remove();
        }
    }

    private String extractIp(HttpServletRequest request) {
        String xff = request.getHeader("X-Forwarded-For");
        if (xff != null && !xff.isBlank()) {
            // X-Forwarded-For 可能是逗号分隔列表，取第一个（最原始的客户端 IP）
            return xff.split(",")[0].trim();
        }
        String xRealIp = request.getHeader("X-Real-IP");
        if (xRealIp != null && !xRealIp.isBlank()) {
            return xRealIp.trim();
        }
        return request.getRemoteAddr();
    }

    /**
     * 请求上下文（IP + UserAgent + 审计 before + 签名 ID）
     */
    public static class RequestContext {
        private final String ip;
        private final String userAgent;
        private String auditBefore;
        private Long signatureId;

        public RequestContext(String ip, String userAgent) {
            this.ip = ip;
            this.userAgent = userAgent;
        }

        public String getIp() { return ip; }
        public String getUserAgent() { return userAgent; }
        public String getAuditBefore() { return auditBefore; }
        public void setAuditBefore(String auditBefore) { this.auditBefore = auditBefore; }
        public Long getSignatureId() { return signatureId; }
        public void setSignatureId(Long signatureId) { this.signatureId = signatureId; }
    }
}
