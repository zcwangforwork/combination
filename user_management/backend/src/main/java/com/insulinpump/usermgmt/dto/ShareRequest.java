package com.insulinpump.usermgmt.dto;

import java.util.List;

/**
 * 分享请求 DTO
 *
 * userIds: 要分享给的同事 ID 列表
 */
public class ShareRequest {

    private List<Long> userIds;

    public List<Long> getUserIds() { return userIds; }
    public void setUserIds(List<Long> userIds) { this.userIds = userIds; }
}
