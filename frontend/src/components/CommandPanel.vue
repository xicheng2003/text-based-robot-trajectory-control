<script setup lang="ts">
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Loader2 } from 'lucide-vue-next'
import CommandGuide from '@/components/CommandGuide.vue' // 1. 导入指令参考组件

defineProps<{
  isLoading: boolean
}>()

const emit = defineEmits<{
  (e: 'sendCommand', command: string): void
}>()

const commandText = ref('')

function submitCommand() {
  emit('sendCommand', commandText.value)
}

function sendPresetCommand(command: string) {
  commandText.value = command
  emit('sendCommand', command)
}
</script>

<template>
  <Card class="w-full">
    <CardHeader>
      <CardTitle>控制面板</CardTitle>
      <CardDescription class="flex items-center gap-2 pt-1">
        <span>可使用自然语言进行控制</span>
        <a href="https://www.deepseek.com" target="_blank" class="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-800 dark:hover:text-gray-200">
          <span>由 </span>
          <img src="https://cdn.deepseek.com/logo.png?x-image-process=image%2Fresize%2Cw_1920" alt="Deepseek Logo" class="h-4">
          <span> 强力驱动 </span>
        </a>
      </CardDescription>
    </CardHeader>
    <CardContent>
      <div class="space-y-4">
        <Textarea
          v-model="commandText"
          placeholder="例如:&#10;让关节1转动30度，然后把速度设为50。&#10;再让X轴前进100毫米，最后全轴回零。"
          rows="8"
          class="text-base dark:bg-slate-800 dark:text-gray-200"
        />

        <Button @click="submitCommand" :disabled="isLoading" class="w-full">
          <Loader2 v-if="isLoading" class="mr-2 h-4 w-4 animate-spin" />
          {{ isLoading ? '执行中...' : '发送指令' }}
        </Button>

        <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Button @click="sendPresetCommand('PAUSE_MOVE')" variant="outline">暂停运动</Button>
          <Button @click="sendPresetCommand('CONTINUE_MOVE')" variant="outline">继续运动</Button>
          <Button @click="sendPresetCommand('STOP_MOVE')" variant="destructive">停止运动</Button>
          <Button @click="sendPresetCommand('GO_HOME_ALL')" variant="secondary">全轴回零</Button>
        </div>

        <div class="border-t pt-4">
          <CommandGuide />
        </div>

      </div>
    </CardContent>
  </Card>
</template>