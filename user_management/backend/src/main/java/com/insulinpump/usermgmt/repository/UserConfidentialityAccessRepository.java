package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.ConfidentialityLevel;
import com.insulinpump.usermgmt.model.UserConfidentialityAccess;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Set;

/**
 * 用户保密等级授权 Repository
 *
 * 关键查询：
 *  - findByUserId: 取某用户的全部授权等级（User 实体 EAGER 加载已用）
 *  - existsByUserIdAndConfidentialityLevel: 判断是否被授权某等级
 *  - deleteByUserIdAndConfidentialityLevel: 撤销某等级授权
 */
@Repository
public interface UserConfidentialityAccessRepository extends JpaRepository<UserConfidentialityAccess, Long> {

    List<UserConfidentialityAccess> findByUserId(Long userId);

    boolean existsByUserIdAndConfidentialityLevel(Long userId, ConfidentialityLevel level);

    void deleteByUserIdAndConfidentialityLevel(Long userId, ConfidentialityLevel level);

    /**
     * 批量查询多个用户的授权等级（用于列表页 accessRole 显示优化，减少 N+1）
     */
    List<UserConfidentialityAccess> findByUserIdIn(Set<Long> userIds);
}
