<script setup lang="ts">
import { RouterView } from 'vue-router'
import Toaster from '@/components/ui/toast/Toaster.vue'
// import ThemeToggle from '@/components/ThemeToggle.vue' // <-- 移除这一行，ThemeToggle 现在在 NavigationBar 里

// 导入新的 NavigationBar 组件
import NavigationBar from './components/NavigationBar.vue';

// 使用 @vueuse/core 库来自动处理 class 的添加/移除
// 保持这部分原有的代码
import { useColorMode } from '@vueuse/core'
useColorMode() // 调用一次即可
</script>

<template>
    <!-- 整个应用的根容器 -->
    <!-- 保留原有的背景色和最小高度设置 -->
    <div class="bg-gray-50 dark:bg-slate-900 min-h-screen flex flex-col">

        <!-- 顶部导航栏 -->
        <!-- NavigationBar 会自动处理固定定位和阴影，不需要这里的 absolute 定位 -->
        <NavigationBar />

        <!-- 主要内容区域 -->
        <!-- RouterView 将会渲染当前路由对应的页面组件 -->
        <!-- 增加 mt-12 (或根据 NavigationBar 实际高度调整) 给固定顶部的导航栏留出空间 -->
        <main class="flex-grow container mx-auto px-4 py-8 mt-12">
             <RouterView />
        </main>

        <!-- Toaster 组件用于显示通知，通常放在根容器的外面或者顶部，以确保它在所有内容的上方 -->
        <!-- 我们将其放在最外层 div 的末尾 -->
    </div>
    <Toaster />

</template>

<style scoped>
/* 如果 App.vue 有全局样式或布局样式，保留在此 */
/* 例如，如果你需要强制 main 占满剩余空间 */
/* main { flex-grow: 1; } */
</style>
