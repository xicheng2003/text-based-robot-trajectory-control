<script setup lang="ts">
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'

const commandGroups = [
  {
    groupName: '基础与设置',
    commands: [
      { name: 'AUTO_MODE', description: '切换机器人到自动模式，是执行运动指令的前提。' },
      { name: 'SET_SPEED [<速度值>]', description: '设置后续运动的速度。如果省略速度值，则使用默认值。示例: SET_SPEED 80' },
    ],
  },
  {
    groupName: '关节与坐标系运动',
    commands: [
      { name: 'MOVE J<1-6> <角度>', description: '让指定关节转动一个增量角度。示例: MOVE J1 30' },
      { name: 'MOVE X/Y/Z/A/B/C <值>', description: '让机器人沿基坐标系移动或旋转一个增量。示例: MOVE X 100' },
    ],
  },
  {
    groupName: '回零与控制',
    commands: [
      { name: 'GO_HOME_ALL', description: '让所有关节回到零点位置。' },
      { name: 'GO_HOME_J<1-6>', description: '让单个指定关节回到零点。示例: GO_HOME_J2' },
      { name: 'PAUSE_MOVE', description: '暂停当前正在进行的运动。' },
      { name: 'CONTINUE_MOVE', description: '继续已暂停的运动。' },
      { name: 'STOP_MOVE', description: '立即停止并取消当前所有运动。' },
    ],
  },
   {
    groupName: '其他',
    commands: [
      { name: 'MONITOR', description: '手动触发一次状态刷新，通常由前端自动轮询。' },
      { name: 'TEST_WRITE_GV0 <值>', description: '向GV0全局变量写入一个浮点数用于测试。示例: TEST_WRITE_GV0 123.45' },
    ],
  },
]
</script>

<template>
  <Accordion type="single" collapsible class="w-full">
    <AccordionItem value="guide">
      <AccordionTrigger class="text-base">
        操作说明及指令参考
      </AccordionTrigger>
      <AccordionContent>
        <div v-for="group in commandGroups" :key="group.groupName" class="mb-4">
          <h4 class="font-semibold text-lg mb-2 text-foreground">{{ group.groupName }}</h4>
          <ul class="space-y-2 list-disc pl-5">
            <li v-for="cmd in group.commands" :key="cmd.name">
              <code class="font-mono bg-muted p-1 rounded-md">{{ cmd.name }}</code>
              <p class="text-muted-foreground text-sm">{{ cmd.description }}</p>
            </li>
          </ul>
        </div>
      </AccordionContent>
    </AccordionItem>
  </Accordion>
</template>
