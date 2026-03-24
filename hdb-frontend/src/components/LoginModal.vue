<script setup lang="ts">
defineProps<{
  open: boolean
  nric: string
  password: string
  error: string
}>()

defineEmits<{
  close: []
  submit: []
  'update:nric': [value: string]
  'update:password': [value: string]
}>()
</script>

<template>
  <transition name="fade">
    <section v-if="open" class="modal-shell" @click.self="$emit('close')">
      <div class="login-card card-surface">
        <button class="login-card__close" type="button" @click="$emit('close')">x</button>
        <p class="section-tag">Secure sign in</p>
        <h3>Continue with your NRIC and password.</h3>
        <p class="login-card__body">
          This redesign keeps login frontend-only for demo purposes while staying closer to a
          professional service portal pattern.
        </p>

        <label class="field">
          <span>NRIC</span>
          <input
            :value="nric"
            type="text"
            placeholder="e.g. S1234567A"
            @input="$emit('update:nric', ($event.target as HTMLInputElement).value)"
          />
        </label>

        <label class="field">
          <span>Password</span>
          <input
            :value="password"
            type="password"
            placeholder="Enter your password"
            @input="$emit('update:password', ($event.target as HTMLInputElement).value)"
          />
        </label>

        <p v-if="error" class="login-card__error">{{ error }}</p>

        <button class="button button--primary login-card__submit" type="button" @click="$emit('submit')">
          Log in
        </button>

        <div class="login-card__demo">
          <strong>Demo access</strong>
          <span>S1234567A / apple123</span>
          <span>S7654321D / redhome</span>
        </div>
      </div>
    </section>
  </transition>
</template>

<style scoped>
.modal-shell {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(23, 23, 23, 0.24);
  backdrop-filter: blur(10px);
}

.login-card {
  position: relative;
  width: min(440px, 100%);
  padding: 28px;
}

.login-card h3 {
  margin: 0;
  font-size: 1.9rem;
  line-height: 1.08;
  letter-spacing: -0.04em;
}

.login-card__body {
  margin: 14px 0 0;
  color: var(--color-text-muted);
  line-height: 1.68;
}

.login-card__close {
  position: absolute;
  top: 14px;
  right: 16px;
  border: none;
  background: transparent;
  color: var(--color-text-soft);
  cursor: pointer;
  font-size: 1.4rem;
}

.field {
  display: grid;
  gap: 8px;
  margin-top: 16px;
}

.field span {
  color: var(--color-text);
  font-size: 0.9rem;
}

.field input {
  width: 100%;
}

.login-card__error {
  margin: 14px 0 0;
  color: var(--color-red);
  font-weight: 600;
}

.login-card__submit {
  width: 100%;
  margin-top: 20px;
}

.login-card__demo {
  display: grid;
  gap: 8px;
  margin-top: 18px;
  padding: 16px;
  border-radius: 20px;
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 180ms ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
