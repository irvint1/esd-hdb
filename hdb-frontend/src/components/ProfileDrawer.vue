<script setup lang="ts">
import type { DemoUser } from '../data/home'

defineProps<{
  open: boolean
  user: DemoUser | null
}>()

defineEmits<{
  close: []
  logout: []
  browse: []
}>()
</script>

<template>
  <transition name="fade">
    <section v-if="open && user" class="drawer-shell" @click.self="$emit('close')">
      <aside class="drawer card-surface">
        <button class="drawer__close" type="button" @click="$emit('close')">Close</button>
        <p class="section-tag">Applicant profile</p>
        <h3>{{ user.name }}</h3>

        <dl class="drawer__details">
          <div>
            <dt>NRIC</dt>
            <dd>{{ user.nric }}</dd>
          </div>
          <div>
            <dt>Age</dt>
            <dd>{{ user.age }}</dd>
          </div>
          <div>
            <dt>Household</dt>
            <dd>{{ user.household }}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{{ user.status }}</dd>
          </div>
          <div>
            <dt>Preferred town</dt>
            <dd>{{ user.preferredTown }}</dd>
          </div>
        </dl>

        <div class="drawer__actions">
          <button class="button button--secondary" type="button" @click="$emit('browse')">
            View launches
          </button>
          <button class="button button--ghost" type="button" @click="$emit('logout')">
            Log out
          </button>
        </div>
      </aside>
    </section>
  </transition>
</template>

<style scoped>
.drawer-shell {
  position: fixed;
  inset: 0;
  z-index: 30;
  display: flex;
  justify-content: flex-end;
  padding: 18px;
  background: rgba(23, 23, 23, 0.16);
}

.drawer {
  width: min(360px, 100%);
  padding: 26px;
}

.drawer h3 {
  margin: 0;
  font-size: 2rem;
  line-height: 1.04;
  letter-spacing: -0.04em;
}

.drawer__close {
  border: none;
  background: transparent;
  color: var(--color-text-soft);
  cursor: pointer;
  font-size: 0.92rem;
}

.drawer__details {
  display: grid;
  gap: 14px;
  margin: 22px 0 0;
}

.drawer__details div {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-border);
}

.drawer__details dt {
  color: var(--color-text-soft);
}

.drawer__details dd {
  margin: 0;
  text-align: right;
  font-weight: 600;
}

.drawer__actions {
  display: flex;
  gap: 12px;
  margin-top: 24px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 180ms ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@media (max-width: 680px) {
  .drawer-shell {
    padding: 0;
  }

  .drawer {
    width: 100%;
    min-height: 100vh;
    border-radius: 0;
  }

  .drawer__actions {
    flex-direction: column;
  }
}
</style>
