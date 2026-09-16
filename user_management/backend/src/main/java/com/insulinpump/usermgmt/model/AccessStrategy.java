package com.insulinpump.usermgmt.model;

/**
 * 数据可见性策略枚举
 *
 * SIMPLE  : owner + ADMIN + 部门领导 + 用户授权等级（用于 ResearchData / CommercialRecord）
 * SHARED  : SIMPLE + DocumentShare 分享机制（用于 ResearchMaterial 研发资料文件）
 */
public enum AccessStrategy {
    SIMPLE,
    SHARED
}
