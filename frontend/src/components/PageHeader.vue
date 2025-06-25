<script setup lang="ts">
// 引入一个机器人图标，让界面更有科技感
import { Bot } from 'lucide-vue-next'
</script>

<template>
  <!-- 
    整体设计思路:
    - 使用上下内边距 (py-8) 创造出开阔的呼吸感。
    - 居中对齐，突出核心信息。
    - 使用一个带背景的图标作为视觉锚点。
    - 主标题使用大字号和微妙的文字渐变色，提升现代感。
    - 副标题解释平台价值，引导用户理解。
  -->
  <div class="space-y-4 text-center py-8">
    
    <!-- 1. 精致的图标容器 -->
    <div class="inline-block rounded-lg bg-muted p-3">
      <Bot class="h-8 w-8 text-primary" />
    </div>
    
    <!-- 2. 更具冲击力的主标题 -->
    <h1 class="text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
      <!-- 对关键词使用渐变色，是现代UI设计的流行手法 -->
      <span class="bg-gradient-to-r from-primary via-blue-500 to-indigo-500 bg-clip-text text-transparent">
        基于文本
      </span>
      的机器人轨迹控制
    </h1>
    
    <!-- 3. 清晰的副标题/Slogan -->
    <p class="max-w-2xl mx-auto text-lg text-muted-foreground">
      赋予机器人理解自然语言的能力，通过简单的文字指令，实现精准的轨迹运动控制。
    </p>
  </div>
</template>
