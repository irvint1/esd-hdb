<script setup lang="ts">
import type { DemoUser } from '../data/home'

defineProps<{
  isLoggedIn: boolean
  currentUser: DemoUser | null
}>()

defineEmits<{
  apply: []
  browse: []
}>()
</script>

<template>
  <section class="hero" id="dashboard">
    <div class="hero__panel card-surface">
      <p class="section-tag">Applicant dashboard</p>
      <h2>A professional, calmer front door to the BTO application journey.</h2>
      <p class="hero__lede">
        Designed around launch awareness, ballot clarity, and flat selection readiness, this
        homepage focuses on the next action instead of overwhelming the user with noise.
      </p>

      <div class="hero__actions">
        <button class="button button--primary" type="button" @click="$emit('apply')">
          {{ isLoggedIn ? 'Resume application' : 'Log in to apply' }}
        </button>
        <button class="button button--secondary" type="button" @click="$emit('browse')">
          View upcoming launches
        </button>
      </div>

      <div class="hero__status-grid">
        <article class="status-card">
          <span class="status-card__label">Current focus</span>
          <strong>{{ isLoggedIn ? 'Application planning' : 'Sign in to continue' }}</strong>
          <p>
            {{
              isLoggedIn
                ? 'Your dashboard is ready with launches, journey guidance, and applicant details.'
                : 'Use your NRIC and password to unlock launch planning and applicant details.'
            }}
          </p>
        </article>

        <article class="status-card">
          <span class="status-card__label">Applicant profile</span>
          <strong>{{ currentUser?.name ?? 'Guest applicant' }}</strong>
          <p>
            {{
              currentUser
                ? `${currentUser.household} • ${currentUser.preferredTown}`
                : 'Demo access available with the sample accounts shown in the login modal.'
            }}
          </p>
        </article>

        <article class="status-card">
          <span class="status-card__label">Launch readiness</span>
          <strong>Upcoming 2026 window</strong>
          <p>Track the next launch timing, compare flat mix, and understand when to act.</p>
        </article>
      </div>
    </div>

    <div class="hero__aside">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.hero {
  display: grid;
  grid-template-columns: minmax(360px, 1.05fr) minmax(320px, 0.95fr);
  gap: 22px;
  align-items: stretch;
  max-width: 1240px;
  margin: 0 auto;
}

.hero__panel {
  padding: 36px;
}

.hero__panel h2 {
  margin: 0;
  font-size: clamp(2.6rem, 4.2vw, 4.8rem);
  line-height: 0.94;
  letter-spacing: -0.055em;
}

.hero__lede {
  max-width: 62ch;
  margin: 18px 0 0;
  color: var(--color-text-muted);
  line-height: 1.72;
}

.hero__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 28px;
}

.hero__status-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-top: 30px;
}

.status-card {
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: 24px;
  background: var(--color-surface-alt);
}

.status-card__label {
  display: block;
  margin-bottom: 8px;
  color: var(--color-text-soft);
  font-size: 0.8rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.status-card strong {
  display: block;
  margin-bottom: 8px;
  font-size: 1rem;
  letter-spacing: -0.02em;
}

.status-card p {
  margin: 0;
  color: var(--color-text-muted);
  line-height: 1.6;
}

.hero__aside {
  display: flex;
}

@media (max-width: 1080px) {
  .hero,
  .hero__status-grid {
    grid-template-columns: 1fr;
  }

  .hero__panel {
    padding: 28px;
  }
}
</style>
