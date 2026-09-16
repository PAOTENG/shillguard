package com.shillguard.content.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.entity.UserFavoriteFolder;
import com.shillguard.content.vo.PostVO;

import java.util.List;

public interface FavoriteService {

    /** 列出当前用户的全部收藏夹（含每个夹的帖子数） */
    List<UserFavoriteFolder> listFolders(Long userId);

    /** 新建收藏夹 */
    UserFavoriteFolder createFolder(Long userId, String folderName);

    /** 删除收藏夹：夹内帖子置为未分组(folder_id=null)，不删除收藏关系 */
    void deleteFolder(Long userId, Long folderId);

    /** 收藏帖子：可选归入某收藏夹(folderId 可空=未分组) */
    void favorite(Long userId, Long postId, Long folderId);

    /** 取消收藏 */
    void unfavorite(Long userId, Long postId);

    /** 我的收藏记录（分页，返回完整帖子） */
    IPage<PostVO> pageFavoritePosts(Long userId, int pageNum, int pageSize, Long currentUserId);
}
