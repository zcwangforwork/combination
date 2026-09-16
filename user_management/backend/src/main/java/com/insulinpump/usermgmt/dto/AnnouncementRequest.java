package com.insulinpump.usermgmt.dto;

/**
 * 系统公告发布请求
 */
public class AnnouncementRequest {

    private String title;
    private String content;

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
}
