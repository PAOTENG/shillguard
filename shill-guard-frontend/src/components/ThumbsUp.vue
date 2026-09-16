<template>
  <!-- 大拇指点赞图标（用 currentColor，可通过 color/CSS 控制颜色；点赞后变红） -->
  <svg
    class="thumbs-up-icon"
    viewBox="0 0 24 24"
    width="1em"
    height="1em"
    fill="currentColor"
    aria-hidden="true"
  >
    <path d="M23 10c0-1.1-.9-2-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.59 7.59C7.22 7.95 7 8.45 7 9v10c0 1.1.9 2 2 2h9c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.11-.23.14-.47.14-.73v-2zM1 9h4v12H1z" />
  </svg>
</template>

<script setup lang="ts">
// 纯展示图标，无 props；大小跟随父元素 font-size（1em），颜色跟随 currentColor。
</script>

<style scoped>
.thumbs-up-icon {
  display: inline-block;
  vertical-align: middle;
}
</style>
