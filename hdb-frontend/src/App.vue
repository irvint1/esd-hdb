<script setup lang="ts">
import { computed, ref } from 'vue'
import DashboardHero from './components/DashboardHero.vue'
import JourneyCarousel from './components/JourneyCarousel.vue'
import LaunchGrid from './components/LaunchGrid.vue'
import LoginModal from './components/LoginModal.vue'
import ProcessTimeline from './components/ProcessTimeline.vue'
import ProfileDrawer from './components/ProfileDrawer.vue'
import TopBar from './components/TopBar.vue'
import {
  demoUsers,
  journeySlides,
  processSteps,
  upcomingLaunches,
  type DemoUser,
} from './data/home'

const launchesSection = ref<HTMLElement | null>(null)
const currentUser = ref<DemoUser | null>(null)
const showLoginModal = ref(false)
const showProfileDrawer = ref(false)
const nric = ref('')
const password = ref('')
const loginError = ref('')

const isLoggedIn = computed(() => currentUser.value !== null)
const displayName = computed(() => currentUser.value?.name ?? 'Guest')

function openLoginModal() {
  loginError.value = ''
  showLoginModal.value = true
}

function closeLoginModal() {
  showLoginModal.value = false
  loginError.value = ''
}

function scrollToLaunches() {
  launchesSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function handlePrimaryAction() {
  if (!isLoggedIn.value) {
    openLoginModal()
    return
  }

  scrollToLaunches()
}

function handleLogin() {
  const normalizedNric = nric.value.trim().toUpperCase()
  const matchedUser = demoUsers.find(
    (user) => user.nric === normalizedNric && user.password === password.value,
  )

  if (!matchedUser) {
    loginError.value = 'Unable to match that NRIC and password. Use one of the demo accounts below.'
    return
  }

  currentUser.value = matchedUser
  closeLoginModal()
  showProfileDrawer.value = false
  scrollToLaunches()
}

function toggleProfileDrawer() {
  if (!isLoggedIn.value) {
    openLoginModal()
    return
  }

  showProfileDrawer.value = !showProfileDrawer.value
}

function closeProfileDrawer() {
  showProfileDrawer.value = false
}

function logout() {
  currentUser.value = null
  showProfileDrawer.value = false
  nric.value = ''
  password.value = ''
}
</script>

<template>
  <div class="page-shell">
    <TopBar
      :display-name="displayName"
      :is-logged-in="isLoggedIn"
      @apply="handlePrimaryAction"
      @toggle-profile="toggleProfileDrawer"
    />

    <main>
      <DashboardHero
        :current-user="currentUser"
        :is-logged-in="isLoggedIn"
        @apply="handlePrimaryAction"
        @browse="scrollToLaunches"
      >
        <JourneyCarousel :slides="journeySlides" />
      </DashboardHero>

      <ProcessTimeline :steps="processSteps" />

      <div ref="launchesSection">
        <LaunchGrid :launches="upcomingLaunches" />
      </div>
    </main>

    <ProfileDrawer
      :open="showProfileDrawer"
      :user="currentUser"
      @browse="scrollToLaunches"
      @close="closeProfileDrawer"
      @logout="logout"
    />

    <LoginModal
      :error="loginError"
      :nric="nric"
      :open="showLoginModal"
      :password="password"
      @close="closeLoginModal"
      @submit="handleLogin"
      @update:nric="nric = $event"
      @update:password="password = $event"
    />
  </div>
</template>

<style scoped>
.page-shell {
  min-height: 100vh;
  padding: 20px 20px 72px;
}

main {
  display: grid;
  gap: 24px;
}

@media (max-width: 720px) {
  .page-shell {
    padding: 14px 14px 56px;
  }
}
</style>
