<script setup lang="ts">
import { computed } from 'vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

// 为机器人状态数据定义清晰的类型
interface RobotStatusData {
  mode: string;
  run_status: string;
  alarm_status: string;
  alarm_code?: number;
  gv0_value: number | string | null;
}

// 接收一个完整的 state 对象
const props = defineProps<{
  state: {
    connected: boolean;
    isLoading: boolean;
    errorMessage: string | null;
    data: RobotStatusData;
  };
  logs: string[];
}>();

// 计算属性，根据不同状态返回不同的 Badge 颜色
const runStatusVariant = computed(() => {
  if (!props.state.connected) return 'destructive'; // 如果未连接，显示危险状态
  switch (props.state.data.run_status) {
    case '正在运行': return 'default'
    case '暂停': return 'secondary'
    case '停止': return 'outline'
    default: return 'destructive'
  }
})

const alarmStatusVariant = computed(() => {
  if (!props.state.connected) return 'destructive';
  return props.state.data.alarm_code === 0 ? 'secondary' : 'destructive'
})
</script>

<template>
  <Card class="w-full">
    <CardHeader>
      <div class="flex items-start justify-between">
        <div>
          <CardTitle>机器人状态与日志</CardTitle>
          <CardDescription>实时监控机器人当前状态</CardDescription>
        </div>
        <!-- 连接状态指示器 -->
        <div class="flex items-center space-x-2 text-sm">
          <span
            class="h-3 w-3 rounded-full"
            :class="{
              'bg-green-500 animate-pulse': state.connected,
              'bg-red-500': !state.connected && !state.isLoading,
              'bg-yellow-500': state.isLoading
            }"
          ></span>
          <span :class="{'text-muted-foreground': state.isLoading}">
            {{ state.isLoading ? '加载中...' : state.connected ? '已连接' : '已断开' }}
          </span>
        </div>
      </div>
    </CardHeader>
    <CardContent>
      <!-- 错误信息提示栏 (已优化颜色) -->
      <div v-if="!state.connected && state.errorMessage"
           class="mb-4 p-3 bg-red-100 dark:bg-destructive/20 border-l-4 border-red-400 dark:border-red-600 text-red-800 dark:text-red-200 rounded-md text-sm">
        <p class="font-bold">连接错误</p>
        <p>{{ state.errorMessage }}</p>
      </div>

      <!-- 状态显示网格 -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-center">
        <div>
          <h4 class="font-semibold text-sm text-muted-foreground">当前模式</h4>
          <p class="text-lg font-bold">{{ state.data.mode }}</p>
        </div>
        <div>
          <h4 class="font-semibold text-sm text-muted-foreground">运行状态</h4>
          <Badge :variant="runStatusVariant">{{ state.data.run_status }}</Badge>
        </div>
        <div>
          <h4 class="font-semibold text-sm text-muted-foreground">报警状态</h4>
          <Badge :variant="alarmStatusVariant">{{ state.data.alarm_status }}</Badge>
        </div>
        <div>
          <h4 class="font-semibold text-sm text-muted-foreground">GV0 测试值</h4>
          <p class="text-lg font-bold">{{ typeof state.data.gv0_value === 'number' ? state.data.gv0_value.toFixed(2) : 'N/A' }}</p>
        </div>
      </div>

      <!-- 日志显示区域 -->
      <div class="bg-muted p-4 rounded-lg border text-sm h-64 overflow-y-auto font-mono">
        <p v-for="(log, index) in logs.slice(0, 100)" :key="index" class="whitespace-pre-wrap break-words">
          {{ log }}
        </p>
      </div>
    </CardContent>
  </Card>
</template>
