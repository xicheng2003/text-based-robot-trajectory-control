<script setup lang="ts">
import { ref, onMounted } from 'vue';
import axios from 'axios';
import Button from '@/components/ui/button/Button.vue';
import Input from '@/components/ui/input/Input.vue';
import Label from '@/components/ui/label/Label.vue';
// --- 新增：导入Tabs组件 ---
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

// script部分的其他所有代码都保持原样，无需改动
interface Settings {
  robot: {
    ip: string;
    port: number;
    slave_id: number;
  };
  motion: {
    default_speed: number;
  };
  server: {
    host: string;
    port: number;
  };
  llm_config: {
    api_key: string;
    model_name: string;
    api_base_url: string;
  };
}

const settings = ref<Partial<Settings>>({});
const isLoading = ref(true);
const errorMessage = ref('');
const successMessage = ref('');

onMounted(async () => {
  try {
    isLoading.value = true;
    errorMessage.value = '';
    const response = await axios.get('/api/settings');
    if (response.data.status === 'success') {
      settings.value = response.data.settings;
    } else {
      throw new Error('Failed to load settings from server.');
    }
  } catch (error: any) {
    errorMessage.value = error.message || 'An unknown error occurred.';
    console.error('Error fetching settings:', error);
  } finally {
    isLoading.value = false;
  }
});

const saveSettings = async () => {
  try {
    isLoading.value = true;
    errorMessage.value = '';
    successMessage.value = '';
    const response = await axios.post('/api/settings', settings.value);
    if (response.data.status === 'success') {
      successMessage.value = response.data.message || 'Settings saved successfully!';
    } else {
      throw new Error(response.data.message || 'Failed to save settings.');
    }
  } catch (error: any) {
    errorMessage.value = error.message || 'An unknown error occurred while saving.';
    console.error('Error saving settings:', error);
  } finally {
    isLoading.value = false;
    setTimeout(() => { successMessage.value = '' }, 3000);
  }
};
</script>

<template>
  <div class="container mx-auto p-4 md:p-6">
    <div class="max-w-2xl mx-auto">
      <div class="flex justify-between items-center mb-6">
        <h1 class="text-3xl font-bold">应用设置</h1>
        <router-link to="/">
          <Button variant="outline">返回主页</Button>
        </router-link>
      </div>

      <div v-if="isLoading" class="text-center text-muted-foreground">正在加载设置...</div>
      <div v-else-if="errorMessage" class="p-4 bg-red-100 text-red-700 rounded-md">{{ errorMessage }}</div>

      <form v-else-if="settings" @submit.prevent="saveSettings" class="space-y-6">
        <Tabs default-value="robot" class="w-full">
          <TabsList class="grid w-full grid-cols-3">
            <TabsTrigger value="robot">
              机器人配置
            </TabsTrigger>
            <TabsTrigger value="motion">
              运动配置
            </TabsTrigger>
            <TabsTrigger value="llm">
              LLM 配置
            </TabsTrigger>
          </TabsList>

          <TabsContent value="robot" class="mt-6 p-6 border rounded-lg">
            <div v-if="settings.robot" class="space-y-4">
              <div>
                <Label for="robot-ip">机器人IP地址</Label>
                <Input id="robot-ip" v-model="settings.robot.ip" />
              </div>
              <div>
                <Label for="robot-port">机器人端口</Label>
                <Input id="robot-port" type="number" v-model.number="settings.robot.port" />
              </div>
              <div>
                <Label for="robot-slave-id">从站ID (Slave ID)</Label>
                <Input id="robot-slave-id" type="number" v-model.number="settings.robot.slave_id" />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="motion" class="mt-6 p-6 border rounded-lg">
            <div v-if="settings.motion" class="space-y-4">
              <div>
                <Label for="motion-speed">默认速度</Label>
                <Input
                  id="motion-speed"
                  type="number"
                  v-model.number="settings.motion.default_speed"
                  min="1"
                  max="100"
                />
                <p class="text-xs text-muted-foreground mt-2">
                  请输入1到100之间的数值，该值将作为机器人运动的默认速度百分比。
                </p>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="llm" class="mt-6 p-6 border rounded-lg">
            <div v-if="settings.llm_config" class="space-y-4">
              <div>
                <Label for="llm-key">API Key</Label>
                <Input id="llm-key" type="password" v-model="settings.llm_config.api_key" />
              </div>
              <div>
                <Label for="llm-model">模型名称</Label>
                <Input id="llm-model" v-model="settings.llm_config.model_name" />
              </div>
              <div>
                <Label for="llm-base-url">API Base URL</Label>
                <Input id="llm-base-url" v-model="settings.llm_config.api_base_url" />
              </div>
            </div>
          </TabsContent>
        </Tabs>

        <div class="flex justify-end items-center gap-4 pt-4">
          <span v-if="successMessage" class="text-green-600">{{ successMessage }}</span>
          <Button type="submit" :disabled="isLoading">
            <span v-if="isLoading">正在保存...</span>
            <span v-else>保存更改</span>
          </Button>
        </div>
      </form>
    </div>
  </div>
</template>
