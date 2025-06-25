<script setup lang="ts">
// 我们需要一个 GitHub 图标，从已经安装的 lucide-vue-next 库中导入
import { Github } from 'lucide-vue-next'
</script>

<template>
  <!-- 
    整体设计思路:
    - 使用 border-t 创建一个优雅的顶部分隔线。
    - 在暗黑模式下，背景色和文字颜色会自动适应。
    - 使用 Grid 布局创建三列，在移动端 (md 以下) 会自动变为单列堆叠。
  -->
  <footer class="w-full mt-12 border-t border-border/40 py-8 text-sm">
    <div class="container mx-auto grid grid-cols-1 md:grid-cols-3 gap-8">

      <!-- 第一列: 学校与项目信息 -->
      <div class="flex flex-col items-center md:items-start text-center md:text-left">
        <div class="flex items-center gap-3 mb-3">
          <img src="https://www.gdut.edu.cn/images2020/footer-logo2.png" alt="GDUT_Logo" class="h-12 w-12 object-contain">
          <div>
            <p class="font-semibold text-lg text-foreground">广东工业大学</p>
            <p class="text-xs text-muted-foreground">Guangdong University of Technology</p>
          </div>
        </div>
        <p class="text-muted-foreground">
          生产实习实训项目：一个基于文本与自然语言的机器人轨迹运动控制平台
        </p>
      </div>

      <!-- 第二列: 关键链接 -->
      <div class="text-center">
        <h3 class="font-semibold text-foreground mb-4">相关链接</h3>
        <ul class="space-y-2">
          <li>
            <a 
              href="https://github.com/xicheng2003/text-based-robot-trajectory-control" 
              target="_blank" 
              rel="noopener noreferrer"
              class="group inline-flex items-center gap-2 text-muted-foreground hover:text-primary transition-colors"
            >
              <Github class="h-4 w-4" />
              <span>查看项目源码</span>
              <span class="opacity-0 group-hover:opacity-100 transition-opacity text-xs">→</span>
            </a>
          </li>
           <li>
            <a 
              href="https://www.deepseek.com" 
              target="_blank" 
              rel="noopener noreferrer"
              class="group inline-flex items-center gap-2 text-muted-foreground hover:text-primary transition-colors"
            >
              <span>自然语言处理由 </span>
              <img src="https://cdn.deepseek.com/logo.png?x-image-process=image%2Fresize%2Cw_1920" alt="Deepseek Logo" class="h-4" />
              <span> 驱动</span>
            </a>
          </li>
        </ul>
      </div>

      <!-- 第三列: 致谢与版权 -->
      <div class="text-center md:text-right text-muted-foreground">
        <h3 class="font-semibold text-foreground mb-4">致谢</h3>
        <p>Made with <span class="text-red-500">❤️</span> by Lin Xicheng (xicheng2003)</p>
        <p>In collaboration with Pei Zhijie, Liu Jinhang and Lin Taimin.</p>
        <p class="mt-2 text-xs">
          由 Vue 3, Vite, Tailwind CSS & shadcn/ui 强力驱动
        </p>
        <p class="mt-4 text-xs">&copy; 2025 ALL RIGHTS RESERVED.</p>
      </div>

    </div>
  </footer>
</template>
