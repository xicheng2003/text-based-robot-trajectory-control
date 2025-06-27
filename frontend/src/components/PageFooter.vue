<script setup lang="ts">
// 这个组件现在不需要任何图标导入了
const REPO_URL = "https://github.com/xicheng2003/text-based-robot-trajectory-control";
const APP_VERSION = "V2.1.8-release";
const currentYear = new Date().getFullYear();
</script>

<template>
  <!--
    核心优化:
    - 使用 dark: 前缀为所有颜色添加了暗色模式的变体。
    - 背景、文字、边框颜色现在都能自动适应主题切换。
  -->
  <footer class="mt-12 dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800/50">
    <div class="container mx-auto px-6 lg:px-8">

      <!--
        上层内容区:
        - 布局调整为在桌面端为三列，About部分更宽。
        - grid-cols-1 在移动端堆叠，md:grid-cols-4 在中等屏幕上为四栏布局，About占两栏。
      -->
      <div class="py-16 grid grid-cols-1 md:grid-cols-4 gap-12 text-sm">


        <!-- 第三列: 致谢 (已调整布局) -->
        <div>
          <h4 class="font-semibold text-slate-900 dark:text-white mb-4">致谢</h4>
          <div class="text-slate-600 dark:text-slate-400 space-y-3 leading-relaxed">
            <p>由 Xicheng2003 用 <span class="text-red-500">❤️</span> 制作</p>
            <p class="text-xs text-slate-500 dark:text-slate-500">
              与 Pei Zhijie, Liu Jinhang, Lin Taimin 合作完成
            </p>
            <!-- 核心优化: 分割线上移，将技术驱动信息作为一个整体 -->
            <div class="pt-3 border-t border-slate-200 dark:border-slate-800/50 space-y-2">
              <a href="https://www.deepseek.com" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1.5 text-slate-600 dark:text-slate-400 hover:text-sky-500 dark:hover:text-sky-400 transition-colors">
                <span class="text-xs">自然语言处理由</span>
                <img src="https://cdn.deepseek.com/logo.png?x-image-process=image%2Fresize%2Cw_1920" alt="Deepseek Logo" class="h-3.5" />
                <span class="text-xs">驱动</span>
              </a>
              <p class="text-xs text-slate-600 dark:text-slate-400">
                页面由 Vue 3, Vite & shadcn/ui 强力驱动
              </p>
            </div>
          </div>
        </div>

        <!-- 第二列: 链接与许可 (已合并) -->
        <div>
          <h4 class="font-semibold text-slate-900 dark:text-white mb-4">相关链接</h4>
          <ul class="space-y-3">
            <li><a :href="REPO_URL" target="_blank" rel="noopener noreferrer" class="text-slate-600 dark:text-slate-400 hover:text-sky-500 dark:hover:text-sky-400 transition-colors">项目源码</a></li>
            <li><a :href="`${REPO_URL}/releases`" target="_blank" rel="noopener noreferrer" class="text-slate-600 dark:text-slate-400 hover:text-sky-500 dark:hover:text-sky-400 transition-colors">最新版本</a></li>
            <li><a :href="`${REPO_URL}/issues`" target="_blank" rel="noopener noreferrer" class="text-slate-600 dark:text-slate-400 hover:text-sky-500 dark:hover:text-sky-400 transition-colors">报告问题</a></li>
          </ul>

          <h4 class="font-semibold text-slate-900 dark:text-white mb-4 mt-8">开源许可</h4>
          <ul class="space-y-3">
            <li>
                <a :href="`${REPO_URL}/blob/main/LICENSE`" target="_blank" rel="noopener noreferrer" class="text-slate-600 dark:text-slate-400 hover:text-sky-500 dark:hover:text-sky-400 transition-colors">许可证 (MIT)</a>
            </li>
          </ul>
        </div>


        <!-- 第三列: 关于项目 (md屏幕下占两栏) -->
        <div class="md:col-span-2">
          <h4 class="font-bold text-slate-900 dark:text-white text-base mb-4">
            关于本项目
          </h4>
          <p class="text-slate-600 dark:text-slate-400 leading-relaxed">
            该项目源于一次富有挑战的大学实习项目，是对先进机器人技术的一次实践性探索。我们基于 Modbus TCP 协议，在人机交互领域开拓了新的前沿，实现了直观的、基于文本的机器人轨迹控制。
          </p>
          <div class="flex items-center gap-3 mt-4 pt-4 border-t border-slate-200 dark:border-slate-800/50">
            <img src="https://www.gdut.edu.cn/images2020/footer-logo2.png" alt="GDUT_Logo" class="h-12 w-12 object-contain bg-white rounded-full p-1.5">
            <div>
              <p class="text-sm text-slate-600 dark:text-slate-400">该项目亦是广东工业大学的一项生产实习实训项目成果</p>
              <p class="text-xs text-slate-500 dark:text-slate-500">Guangdong University of Technology</p>
            </div>
          </div>
        </div>



      </div>

      <!-- 下层版权区 -->
      <div class="flex flex-col sm:flex-row justify-between items-center border-t border-slate-200 dark:border-slate-800 py-6">
        <div class="text-sm text-slate-500 dark:text-slate-400">
          Copyright © {{ currentYear }} Text-based Robot Trajectory Control. All Rights Reserved.
        </div>
        <!-- 核心优化: 将 GitHub 图标替换为版本号文本 -->
        <div class="text-sm text-slate-500 dark:text-slate-400 mt-4 sm:mt-0">
          {{ APP_VERSION }}
        </div>
      </div>
    </div>
  </footer>
</template>
