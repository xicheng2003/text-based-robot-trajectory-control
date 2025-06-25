<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import CommandPanel from '@/components/CommandPanel.vue'
import StatusPanel from '@/components/StatusPanel.vue'
import PageFooter from '@/components/PageFooter.vue'
import { useToast } from '@/components/ui/toast/use-toast'

// 使用 shadcn-vue 的 Toast (轻提示) 功能来显示消息
const { toast } = useToast()

// --- 响应式状态定义 ---

// 机器人状态
const robotStatus = ref<Record<string, any>>({
  mode: '未知',
  run_status: '未知',
  alarm_status: '未知',
  gv0_value: 'N/A'
})

// 日志消息列表
const logMessages = ref<string[]>([])

// 是否正在加载 (用于显示加载动画)
const isLoading = ref(false)

// 轮询定时器的ID
let pollingInterval: number | undefined

// --- 函数定义 ---

// 添加日志的辅助函数
function addLog(message: string) {
  const time = new Date().toLocaleTimeString()
  logMessages.value.unshift(`[${time}] ${message}`) // 在数组开头添加新日志
}

// 处理从 CommandPanel 发送过来的指令
async function handleSendCommand(command: string) {
  if (!command.trim()) {
    toast({
      title: '错误',
      description: '指令不能为空！',
      variant: 'destructive'
    })
    return
  }

  isLoading.value = true
  addLog(`发送指令批次:\n"${command.split('\n').map(c => `- ${c.trim()}`).join('\n')}"`)
  stopPolling() // 发送新指令前停止旧的轮询

  try {
    // 注意: URL 使用了 /api 前缀来匹配 vite.config.ts 中的代理设置
    const response = await fetch('/api/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ commands: command })
    })

    const data = await response.json()

    if (!response.ok) {
      throw new Error(data.message || '未知服务器错误')
    }
    
    // 处理后端返回的详细结果
    data.detailed_results?.forEach((res: any) => {
        addLog(`> "${res.command}": ${res.message} (${res.status})`);
    });

    if (data.robot_status) {
      robotStatus.value = data.robot_status
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
    toast({
      title: '请求失败',
      description: errorMessage,
      variant: 'destructive'
    })
  } finally {
    isLoading.value = false
  }
}

// 轮询机器人状态
async function pollRobotStatus() {
  try {
    const response = await fetch('/api/status')
    const data = await response.json()
    if (data.status === 'success') {
      robotStatus.value = data.robot_status
      // 如果机器人停止且无报警，则停止轮询
      if (data.robot_status.run_status === '停止' && data.robot_status.alarm_code === 0) {
        stopPolling()
        addLog('机器人运动完成，状态轮询已自动停止。')
      }
    }
  } catch (error) {
    addLog('状态轮询请求失败，已停止轮询。')
    stopPolling()
  }
}

function startPolling(interval = 1000) {
  stopPolling() // 先确保没有正在运行的轮询
  addLog(`状态轮询已启动，间隔: ${interval}ms`)
  pollingInterval = setInterval(pollRobotStatus, interval)
}

function stopPolling() {
  if (pollingInterval) {
    clearInterval(pollingInterval)
    pollingInterval = undefined
  }
}

// 组件加载时获取一次初始状态
onMounted(() => {
  addLog('欢迎使用机器人控制系统。')
  pollRobotStatus()
})

// 组件卸载时确保清除定时器，防止内存泄漏
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
      <StatusPanel 
        :status="robotStatus" 
        :logs="logMessages" 
      />
    </div>
    
    <PageFooter />
  </div>
</template>