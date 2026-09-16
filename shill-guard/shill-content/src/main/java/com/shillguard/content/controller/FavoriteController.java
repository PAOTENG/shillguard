package com.shillguard.content.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.entity.UserFavoriteFolder;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.Result;
import com.shillguard.common.result.ResultCode;
import com.shillguard.content.service.FavoriteService;
import com.shillguard.content.vo.PostVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@Tag(name = "收藏接口")
@RestController
@RequestMapping("/api/content/favorites")
@RequiredArgsConstructor
public class FavoriteController {

    private final FavoriteService favoriteService;

    @Operation(summary = "我的收藏夹列表")
    @GetMapping("/folders")
    public Result<List<UserFavoriteFolder>> folders(@RequestHeader("X-User-Id") Long userId) {
        return Result.success(favoriteService.listFolders(userId));
    }

    @Operation(summary = "新建收藏夹")
    @PostMapping("/folders")
    public Result<UserFavoriteFolder> createFolder(@RequestHeader("X-User-Id") Long userId,
                                                   @RequestParam(name = "name") String name) {
        return Result.success(favoriteService.createFolder(userId, name));
    }

    @Operation(summary = "删除收藏夹（夹内收藏转为未分组）")
    @DeleteMapping("/folders/{folderId}")
    public Result<Void> deleteFolder(@RequestHeader("X-User-Id") Long userId,
                                     @PathVariable("folderId") Long folderId) {
        favoriteService.deleteFolder(userId, folderId);
        return Result.success();
    }

    @Operation(summary = "收藏帖子（可选归入某收藏夹）")
    @PostMapping
    public Result<Void> favorite(@RequestHeader("X-User-Id") Long userId,
                                 @RequestParam(name = "postId") Long postId,
                                 @RequestParam(name = "folderId", required = false) Long folderId) {
        if (userId == null) throw new BizException(ResultCode.UNAUTHORIZED);
        favoriteService.favorite(userId, postId, folderId);
        return Result.success();
    }

    @Operation(summary = "取消收藏")
    @DeleteMapping("/{postId}")
    public Result<Void> unfavorite(@RequestHeader("X-User-Id") Long userId,
                                   @PathVariable("postId") Long postId) {
        favoriteService.unfavorite(userId, postId);
        return Result.success();
    }

    @Operation(summary = "我的收藏记录（完整帖子分页）")
    @GetMapping("/posts")
    public Result<IPage<PostVO>> favoritePosts(
            @RequestParam(name = "pageNum", defaultValue = "1") int pageNum,
            @RequestParam(name = "pageSize", defaultValue = "20") int pageSize,
            @RequestHeader("X-User-Id") Long userId) {
        if (userId == null) throw new BizException(ResultCode.UNAUTHORIZED);
        return Result.success(favoriteService.pageFavoritePosts(userId, pageNum, pageSize, userId));
    }
}
