package com.insulinpump.usermgmt.dto;

/**
 * 通知统计 DTO（顶栏角标数据）
 *
 *  - unreadCount  未读通知总数
 *  - todoCount    未处理审批待办数（= 未读的 APPROVAL_TASK，通常只对 ADMIN 非零）
 */
public class NotificationStatsDto {

    private long unreadCount;
    private long todoCount;

    public NotificationStatsDto() {}

    public NotificationStatsDto(long unreadCount, long todoCount) {
        this.unreadCount = unreadCount;
        this.todoCount = todoCount;
    }

    public long getUnreadCount() { return unreadCount; }
    public void setUnreadCount(long unreadCount) { this.unreadCount = unreadCount; }

    public long getTodoCount() { return todoCount; }
    public void setTodoCount(long todoCount) { this.todoCount = todoCount; }
}
