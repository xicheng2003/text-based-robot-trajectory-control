<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import CommandPanel from '@/components/CommandPanel.vue'
import StatusPanel from '@/components/StatusPanel.vue'
import PageFooter from '@/components/PageFooter.vue'
import { useToast } from '@/components/ui/toast/use-toast'

const { toast } = useToast()

// --- 响应式状态定义 ---

// 为机器人状态数据定义一个清晰的类型
interface RobotStatusData {
  mode: string;
  run_status: string;
  alarm_status: string;
  alarm_code?: number;
  gv0_value: number | string | null; // 允许 'N/A'
}

// 核心改动：用一个更全面的对象来管理状态，取代之前的 robotStatus
const robotState = ref({
  connected: false, // 追踪连接状态
  isLoading: true, // 追踪初始加载状态
  errorMessage: null as string | null, // 存储错误信息
  data: {
    mode: '连接中...',
    run_status: '连接中...',
    alarm_status: '连接中...',
    gv0_value: 'N/A'
  } as RobotStatusData
});

// 日志消息列表 (保持不变)
const logMessages = ref<string[]>([])

// 是否正在加载 (现在可以由 robotState.isLoading 控制，但为保持 CommandPanel 兼容性，暂时保留)
const isLoading = ref(false)

// 轮询定时器的ID (保持不变)
let pollingInterval: number | undefined

// --- 函数定义 ---

// 添加日志的辅助函数 (保持不变)
function addLog(message: string) {
  const time = new Date().toLocaleTimeString()
  logMessages.value.unshift(`[${time}] ${message}`)
}

// 处理从 CommandPanel 发送过来的指令 (更新错误处理逻辑)
async function handleSendCommand(command: string) {
  if (!command.trim()) {
    toast({ title: '错误', description: '指令不能为空！', variant: 'destructive' })
    return
  }

  isLoading.value = true
  addLog(`发送指令批次:\n"${command.split('\n').map(c => `- ${c.trim()}`).join('\n')}"`)
  stopPolling()

  try {
    const response = await fetch('/api/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ commands: command })
    })

    const data = await response.json()

    if (!response.ok) {
      throw new Error(data.message || '未知服务器错误')
    }

    data.detailed_results?.forEach((res: any) => {
        addLog(`> "${res.command}": ${res.message} (${res.status})`);
    });

    if (data.robot_status) {
      // 核心改动：更新整个 robotState
      robotState.value.connected = true;
      robotState.value.errorMessage = null;
      robotState.value.data = data.robot_status;
    }

    if (data.status === 'success' && data.motion_started) {
      toast({ title: '成功', description: '运动已启动，开始轮询状态。' })
      startPolling()
    } else if (data.status === 'error') {
       toast({ title: '指令错误', description: data.message, variant: 'destructive' })
    } else {
       toast({ title: '操作完成', description: '指令已执行，但未启动运动。' })
    }

  } catch (error: any) {
    const errorMessage = error.message || '网络或服务器连接失败'
    addLog(`错误: ${errorMessage}`)
    toast({ title: '请求失败', description: errorMessage, variant: 'destructive' })

    // 核心改动：在捕获到错误时，更新连接状态
    robotState.value.connected = false;
    robotState.value.errorMessage = errorMessage;
    robotState.value.data = { mode: '失败', run_status: '失败', alarm_status: '失败', gv0_value: 'N/A' };

  } finally {
    isLoading.value = false
  }
}

// 轮询机器人状态 (更新错误处理逻辑)
async function pollRobotStatus() {
  // 初始加载时，将 isLoading 设为 true
  if (robotState.value.isLoading) {
    isLoading.value = true;
  }

  try {
    const response = await fetch('/api/status')
    const data = await response.json()

    if (!response.ok) {
        throw new Error(data.message || `服务器响应错误 (HTTP ${response.status})`);
    }

    if (data.status === 'success') {
      // 核心改动：更新整个 robotState
      robotState.value.connected = true;
      robotState.value.errorMessage = null;
      robotState.value.data = data.robot_status;

      if (data.robot_status.run_status === '停止' && data.robot_status.alarm_code === 0) {
        stopPolling()
        addLog('机器人运动完成，状态轮询已自动停止。')
      }
    } else {
        throw new Error(data.message || '获取状态失败');
    }
  } catch (error: any) {
    addLog(`状态轮询请求失败: ${error.message}`)

    // 核心改动：在捕获到错误时，更新连接状态
    robotState.value.connected = false;
    robotState.value.errorMessage = error.message || '无法连接到后端服务。';
    robotState.value.data = { mode: '失败', run_status: '失败', alarm_status: '失败', gv0_value: 'N/A' };

    stopPolling(); // 发生错误时停止轮询
  } finally {
    // 无论成功与否，都结束加载状态
    robotState.value.isLoading = false;
    isLoading.value = false;
  }
}

// (startPolling, stopPolling, onMounted, onUnmounted 函数保持不变)
function startPolling(interval = 1000) {
  stopPolling()
  addLog(`状态轮询已启动，间隔: ${interval}ms`)
  pollingInterval = setInterval(pollRobotStatus, interval)
}

function stopPolling() {
  if (pollingInterval) {
    clearInterval(pollingInterval)
    pollingInterval = undefined
  }
}

onMounted(() => {
  addLog('欢迎使用机器人控制系统。')
  robotState.value.isLoading = true; // 开始时设置为加载中
  pollRobotStatus()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="container mx-auto p-4 md:p-8 space-y-6">
    <PageHeader />

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <CommandPanel
        :is-loading="isLoading"
        @send-command="handleSendCommand"
      />
      <!-- 核心改动：将整个 robotState 对象作为 'state' prop 传入，而不是旧的 robotStatus -->
      <StatusPanel
        :state="robotState"
        :logs="logMessages"
      />
    </div>

    <PageFooter />
  </div>
</template>
