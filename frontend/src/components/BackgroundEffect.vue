<template>
  <!--
    这个 div 是整个背景效果的容器。
    - `aria-hidden="true"`: 告诉屏幕阅读器等辅助技术忽略这个纯装饰性元素。
    - `absolute inset-0`: 绝对定位，并拉伸至其父容器的全部大小。
    - `-z-50`: 确保它位于所有内容的最后面。
    - `overflow-hidden`: 防止光晕的某些部分溢出容器，导致不必要的滚动条。
  -->
  <div aria-hidden="true" class="absolute inset-0 -z-50 overflow-hidden">
    <!-- 每一个 div 代表一个光晕效果 -->
    <div class="aurora-orb absolute left-1/2 top-0 -z-10 h-[40rem] w-[80rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_center,rgba(6,182,212,0.15),transparent_40%)]"></div>
    <div class="aurora-orb absolute -left-[15rem] -bottom-[5rem] -z-10 h-[30rem] w-[50rem] rounded-full bg-[radial-gradient(circle_at_center,rgba(124,58,237,0.1),transparent_50%)]"></div>
    <div class="aurora-orb absolute -right-[15rem] top-[5rem] -z-10 h-[30rem] w-[50rem] rounded-full bg-[radial-gradient(circle_at_center,rgba(2,132,199,0.12),transparent_50%)]"></div>
    <div class="aurora-orb absolute bottom-0 left-1/2 -z-10 h-[30rem] w-[60rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_center,rgba(234,179,8,0.08),transparent_50%)]"></div>
  </div>
</template>

<style>
/*
  注意：这里的 <style> 标签没有 "scoped" 属性。
  这是因为 @keyframes (动画关键帧) 需要在全局范围内定义才能正常工作。
  如果加上 scoped，Vue 会给选择器添加哈希值，可能导致动画失效。
*/

/* 定义通用的漂浮动画 */
@keyframes float {
  0% { transform: translate(0, 0) rotate(0deg); }
  50% { transform: translate(30px, -40px) rotate(15deg); }
  100% { transform: translate(0, 0) rotate(0deg); }
}

/* 定义一个只有垂直方向的漂浮动画 */
@keyframes float-vertical {
  0% { transform: translate(0, 0) rotate(0deg); }
  50% { transform: translate(0, -20px) rotate(-3deg); }
  100% { transform: translate(0, 0) rotate(0deg); }
}

/* 将动画应用到所有光晕元素上 */
.aurora-orb {
  animation: float 25s infinite ease-in-out;
}

/* 为每个光晕设置不同的动画延迟和时长，以创造自然、不同步的动态效果 */
.aurora-orb:nth-of-type(2) {
  animation-delay: -8s;
  animation-duration: 30s;
}

.aurora-orb:nth-of-type(3) {
  animation-delay: -15s;
  animation-duration: 35s;
}

.aurora-orb:nth-of-type(4) {
  animation-name: float-vertical;
  animation-delay: -5s;
  animation-duration: 40s;
}
</style>
