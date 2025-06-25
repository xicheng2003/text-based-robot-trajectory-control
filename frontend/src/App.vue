<script setup lang="ts">
import { RouterView } from 'vue-router'
import Toaster from '@/components/ui/toast/Toaster.vue'
import ThemeToggle from '@/components/ThemeToggle.vue' // 导入新组件

// 使用 @vueuse/core 库来自动处理 class 的添加/移除
import { useColorMode } from '@vueuse/core'
useColorMode() // 调用一次即可
</script>

<template>
  <div class="bg-gray-50 dark:bg-slate-900 min-h-screen">
    <div class="absolute top-4 right-4 z-50">
      <ThemeToggle />
    </div>

    <RouterView />
    <Toaster />
  </div>
</template>