package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.UserCategoryAccess;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Set;

/**
 * 用户资料分类授权 Repository
 *
 * 关键查询：
 *  - findByUserId: 取某用户的全部授权分类（User 实体 EAGER 加载已用）
 *  - existsByUserIdAndCategoryId: 判断是否被授权某分类
 *  - deleteByUserIdAndCategoryId: 撤销某分类授权
 *  - findByUserIdIn: 批量查询多用户的授权分类（列表页 accessRole 显示优化，减少 N+1）
 */
@Repository
public interface UserCategoryAccessRepository extends JpaRepository<UserCategoryAccess, Long> {

    List<UserCategoryAccess> findByUserId(Long userId);

    boolean existsByUserIdAndCategoryId(Long userId, Long categoryId);

    void deleteByUserIdAndCategoryId(Long userId, Long categoryId);

    /**
     * 批量查询多个用户的授权分类（用于列表页 accessRole 显示优化，减少 N+1）
     */
    List<UserCategoryAccess> findByUserIdIn(Set<Long> userIds);
}
