package com.insulinpump.usermgmt.util;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/**
 * SHA-256 校验工具类
 *
 * 统一提供 checksum 计算能力，供三处复用：
 *  - DocumentService (上传/发布时计算 checksum)
 *  - DocumentService (下载时重算校验)
 *  - SignatureService (签名哈希计算)
 *
 * ALCOA+ 数据完整性要求：同一输入必须产生同一输出，确定性算法。
 */
public final class ChecksumUtil {

    private ChecksumUtil() {}

    /**
     * 计算字节数组的 SHA-256 哈希（十六进制小写字符串，64 字符）
     */
    public static String sha256(byte[] data) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(md.digest(data));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 不可用", e);
        }
    }

    /**
     * 计算字符串的 SHA-256 哈希（UTF-8 编码）
     */
    public static String sha256(String data) {
        return sha256(data.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    /**
     * 校验字节数组的 checksum 是否匹配
     * @param data 原始数据
     * @param expectedChecksum 期望的 SHA-256 哈希
     * @return true 如果匹配
     */
    public static boolean verify(byte[] data, String expectedChecksum) {
        if (expectedChecksum == null || expectedChecksum.isBlank()) {
            return false;
        }
        return sha256(data).equalsIgnoreCase(expectedChecksum);
    }
}
