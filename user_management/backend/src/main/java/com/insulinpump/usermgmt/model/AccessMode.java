package com.insulinpump.usermgmt.model;

/**
 * 授权访问模式
 *
 * 用于用户级数据授权（保密等级授权 / 资料分类授权），在"可见"基础上细分操作权限：
 *   READ_ONLY  - 只读：被授权人仅可查看对应范围的数据
 *   READ_WRITE - 可读写：被授权人除查看外，还可新增/修改/删除该范围内的数据
 *
 * 兼容性：历史授权记录该字段为 NULL 时，按 READ_ONLY 处理（最小权限原则）。
 * 判定入口：DataVisibilityChecker.canModify。
 */
public enum AccessMode {
    READ_ONLY,
    READ_WRITE
}
