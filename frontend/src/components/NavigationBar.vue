<script setup lang="ts">
import { ref } from 'vue';
import ThemeToggle from './ThemeToggle.vue';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Share2Icon, Loader2 } from 'lucide-vue-next';
import QrcodeVue from 'qrcode.vue';

const showShareModal = ref(false);
const shareUrl = ref('');
const shareError = ref('');
const isLoading = ref(false);

const openShareModal = async () => {
    showShareModal.value = true;
    isLoading.value = true;
    shareUrl.value = '';
    shareError.value = '';

    try {
        const response = await fetch('/api/server_info');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        if (data.status === 'success') {
            if (data.ip && data.port) {
                shareUrl.value = `http://${data.ip}:${data.port}`;
            } else {
                 shareError.value = '未能获取有效的服务器IP或端口信息。请检查后端日志。';
            }
        } else {
            shareError.value = data.message || '获取服务器信息失败。后端返回错误。';
        }
    } catch (error: any) {
        console.error("获取服务器信息时发生错误:", error);
        shareError.value = `获取服务器信息时发生网络或解析错误: ${error.message}。请确保后端服务正在运行且网络可达。`;
    } finally {
        isLoading.value = false;
    }
};

const copyUrlToClipboard = async () => {
    if (shareUrl.value) {
        try {
            await navigator.clipboard.writeText(shareUrl.value);
            alert('链接已复制到剪贴板！');
        } catch (err) {
            console.error('复制到剪贴板失败:', err);
            alert('复制链接失败，请手动复制。');
        }
    }
};
</script>

<template>
    <!-- 导航栏容器 -->
    <!-- 关键修改：
         1. 移除了 sticky, top-0, z-50，使其变为静态，随页面滚动。
         2. 移除了所有背景、边框和阴影相关的类（如 bg-background/80, backdrop-blur-sm, border-b, shadow-md）。
            这样它会自动继承父元素的背景色。
    -->
    <nav class="w-full px-4 md:px-6 py-3 flex items-center justify-between text-foreground">
        <!-- 左侧标题 -->
        <div class="text-lg md:text-xl font-bold text-primary">
            Text-based Robot Trajectory Control
        </div>

        <!-- 右侧按钮区域 -->
        <div class="flex items-center gap-3">
            <!-- 分享按钮 -->
            <Button variant="outline" size="icon" @click="openShareModal">
                 <Share2Icon class="h-5 w-5" />
                 <span class="sr-only">分享</span>
            </Button>

            <!-- 主题切换按钮 -->
            <ThemeToggle />
        </div>
    </nav>

    <!-- 分享模态框 (Dialog) 部分保持不变 -->
    <Dialog v-model:open="showShareModal">
        <DialogContent>
            <DialogHeader>
                <DialogTitle>分享控制面板链接</DialogTitle>
                <DialogDescription>
                    让同一局域网内的设备扫描下方二维码或访问链接：
                </DialogDescription>
            </DialogHeader>

            <div class="py-4 flex flex-col items-center">
                <div v-if="isLoading" class="flex items-center text-muted-foreground">
                    <Loader2 class="mr-2 h-4 w-4 animate-spin" /> 正在获取服务器信息...
                </div>
                <div v-else-if="shareError" class="text-red-500 text-center">
                    {{ shareError }}
                </div>
                <div v-else-if="shareUrl" class="flex flex-col items-center w-full">
                    <div class="mb-4 p-2 border rounded bg-muted text-muted-foreground text-sm break-all w-full text-center">
                        {{ shareUrl }}
                    </div>
                    <QrcodeVue :value="shareUrl" :size="200" level="H" class="p-2 border border-gray-200 bg-white rounded shadow-sm" />
                    <p class="text-xs text-gray-500 mt-4 text-center">
                         请确保后端程序正在运行，并且设备在同一网络下。
                    </p>
                </div>
            </div>

             <DialogFooter class="flex justify-end gap-2">
                 <Button v-if="shareUrl" variant="secondary" @click="copyUrlToClipboard">复制链接</Button>
             </DialogFooter>
        </DialogContent>
    </Dialog>
</template>
