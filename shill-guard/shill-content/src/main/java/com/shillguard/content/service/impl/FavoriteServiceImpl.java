package com.shillguard.content.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.shillguard.common.entity.ContentPost;
import com.shillguard.common.entity.UserFavorite;
import com.shillguard.common.entity.UserFavoriteFolder;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.ResultCode;
import com.shillguard.content.mapper.FavoriteFolderMapper;
import com.shillguard.content.mapper.FavoriteMapper;
import com.shillguard.content.mapper.PostMapper;
import com.shillguard.content.mapper.UserMapper;
import com.shillguard.content.service.FavoriteService;
import com.shillguard.content.service.support.PostEnricher;
import com.shillguard.content.vo.PostVO;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class FavoriteServiceImpl implements FavoriteService {

    private final FavoriteMapper favoriteMapper;
    private final FavoriteFolderMapper folderMapper;
    private final PostMapper postMapper;
    private final UserMapper userMapper;
    private final PostEnricher postEnricher;

    @Override
    public List<UserFavoriteFolder> listFolders(Long userId) {
        LambdaQueryWrapper<UserFavoriteFolder> w = new LambdaQueryWrapper<UserFavoriteFolder>()
                .eq(UserFavoriteFolder::getUserId, userId)
                .orderByAsc(UserFavoriteFolder::getCreatedTime);
        return folderMapper.selectList(w);
    }

    @Override
    public UserFavoriteFolder createFolder(Long userId, String folderName) {
        if (folderName == null || folderName.isBlank()) {
            throw new BizException(ResultCode.PARAM_ERROR);
        }
        UserFavoriteFolder folder = new UserFavoriteFolder();
        folder.setUserId(userId);
        folder.setFolderName(folderName.trim());
        folder.setPostCount(0L);
        folderMapper.insert(folder);
        return folder;
    }

    @Override
    @Transactional
    public void deleteFolder(Long userId, Long folderId) {
        // 校验这个夹子确实是当前用户的
        UserFavoriteFolder folder = folderMapper.selectById(folderId);
        if (folder == null || !folder.getUserId().equals(userId)) {
            throw new BizException(ResultCode.NOT_FOUND);
        }
        // 把夹内收藏置为未分组（folder_id=null），不删除收藏关系
        UserFavorite update = new UserFavorite();
        update.setFolderId(null);
        LambdaQueryWrapper<UserFavorite> w = new LambdaQueryWrapper<UserFavorite>()
                .eq(UserFavorite::getFolderId, folderId);
        favoriteMapper.update(update, w);
        folderMapper.deleteById(folderId);
    }

    @Override
    @Transactional
    public void favorite(Long userId, Long postId, Long folderId) {
        // 帖子必须存在且审核通过
        ContentPost post = postMapper.selectById(postId);
        if (post == null || post.getStatus() != 0) {
            throw new BizException(ResultCode.POST_NOT_FOUND);
        }
        // 已收藏过则直接返回（幂等）
        UserFavorite existing = favoriteMapper.selectOne(new LambdaQueryWrapper<UserFavorite>()
                .eq(UserFavorite::getUserId, userId)
                .eq(UserFavorite::getPostId, postId));
        if (existing != null) {
            return;
        }
        // 若指定了收藏夹，校验归属
        if (folderId != null) {
            UserFavoriteFolder folder = folderMapper.selectById(folderId);
            if (folder == null || !folder.getUserId().equals(userId)) {
                throw new BizException(ResultCode.NOT_FOUND);
            }
        }
        UserFavorite fav = new UserFavorite();
        fav.setUserId(userId);
        fav.setPostId(postId);
        fav.setFolderId(folderId);
        favoriteMapper.insert(fav);
        // 收藏夹帖子数 +1
        if (folderId != null) {
            folderMapper.updatePostCount(folderId, 1);
        }
        // 维护作者的被收藏数 +1
        userMapper.incrementFavoritedCountByPost(postId, 1);
    }

    @Override
    @Transactional
    public void unfavorite(Long userId, Long postId) {
        UserFavorite fav = favoriteMapper.selectOne(new LambdaQueryWrapper<UserFavorite>()
                .eq(UserFavorite::getUserId, userId)
                .eq(UserFavorite::getPostId, postId));
        if (fav == null) {
            return;
        }
        favoriteMapper.deleteById(fav.getFavoriteId());
        // 收藏夹帖子数 -1
        if (fav.getFolderId() != null) {
            folderMapper.updatePostCount(fav.getFolderId(), -1);
        }
        // 维护作者的被收藏数 -1
        userMapper.incrementFavoritedCountByPost(postId, -1);
    }

    @Override
    public IPage<PostVO> pageFavoritePosts(Long userId, int pageNum, int pageSize, Long currentUserId) {
        IPage<ContentPost> page = favoriteMapper.pageFavoritePosts(new Page<>(pageNum, pageSize), userId);
        return postEnricher.enrichPage(page, currentUserId);
    }
}
