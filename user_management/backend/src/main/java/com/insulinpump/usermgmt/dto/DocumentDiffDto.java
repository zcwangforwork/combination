package com.insulinpump.usermgmt.dto;

import java.util.List;

/**
 * 文档版本对比结果 DTO
 *
 * 对比两个修订版本的元数据字段差异，不解析文件内容。
 * 当 checksum 不同时，contentChanged=true，表示文件内容已变更。
 */
public class DocumentDiffDto {

    private String fromVersion;
    private String toVersion;
    private List<FieldChange> changes;
    private boolean contentChanged;

    public DocumentDiffDto() {}

    public DocumentDiffDto(String fromVersion, String toVersion,
                           List<FieldChange> changes, boolean contentChanged) {
        this.fromVersion = fromVersion;
        this.toVersion = toVersion;
        this.changes = changes;
        this.contentChanged = contentChanged;
    }

    public String getFromVersion() { return fromVersion; }
    public void setFromVersion(String fromVersion) { this.fromVersion = fromVersion; }

    public String getToVersion() { return toVersion; }
    public void setToVersion(String toVersion) { this.toVersion = toVersion; }

    public List<FieldChange> getChanges() { return changes; }
    public void setChanges(List<FieldChange> changes) { this.changes = changes; }

    public boolean isContentChanged() { return contentChanged; }
    public void setContentChanged(boolean contentChanged) { this.contentChanged = contentChanged; }

    /**
     * 单个字段变更
     */
    public static class FieldChange {
        private String field;
        private Object oldValue;
        private Object newValue;

        public FieldChange() {}

        public FieldChange(String field, Object oldValue, Object newValue) {
            this.field = field;
            this.oldValue = oldValue;
            this.newValue = newValue;
        }

        public String getField() { return field; }
        public void setField(String field) { this.field = field; }

        public Object getOldValue() { return oldValue; }
        public void setOldValue(Object oldValue) { this.oldValue = oldValue; }

        public Object getNewValue() { return newValue; }
        public void setNewValue(Object newValue) { this.newValue = newValue; }
    }
}
