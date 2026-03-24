<script setup lang="ts">
defineProps<{
  isLoggedIn: boolean
  displayName: string
}>()

defineEmits<{
  apply: []
  toggleProfile: []
}>()
</script>

<template>
  <header class="topbar card-surface">
    <div class="brandmark">
      <div class="brandmark__crest">BTO</div>
      <div>
        <p class="section-tag">Singapore Home Application Portal</p>
        <h1>HDB Flat Application</h1>
      </div>
    </div>

    <nav class="topbar__nav">
      <a href="#dashboard">Dashboard</a>
      <a href="#journey">Journey</a>
      <a href="#launches">Launches</a>
    </nav>

    <div class="topbar__actions">
      <button class="button button--secondary" type="button" @click="$emit('apply')">
        {{ isLoggedIn ? 'Continue application' : 'Apply now' }}
      </button>

      <button class="profile-button" type="button" @click="$emit('toggleProfile')">
        <span class="profile-button__avatar">{{ displayName.slice(0, 1) }}</span>
        <span class="profile-button__copy">
          <strong>{{ displayName }}</strong>
          <small>{{ isLoggedIn ? 'Open applicant details' : 'Sign in to continue' }}</small>
        </span>
      </button>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  position: sticky;
  top: 16px;
  z-index: 20;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 24px;
  margin: 0 auto 28px;
  max-width: 1240px;
  padding: 18px 22px;
}

.brandmark {
  display: flex;
  align-items: center;
  gap: 16px;
}

.brandmark__crest {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  border-radius: 16px;
  background: var(--color-red);
  color: white;
  font-size: 0.9rem;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.brandmark h1 {
  margin: 0;
  font-size: 1.05rem;
  letter-spacing: -0.02em;
}

.topbar__nav {
  display: flex;
  justify-content: center;
  gap: 22px;
}

.topbar__nav a {
  color: var(--color-text-muted);
  text-decoration: none;
  font-size: 0.94rem;
}

.topbar__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.profile-button {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px 8px 8px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: white;
  cursor: pointer;
  transition:
    transform 180ms ease,
    box-shadow 180ms ease,
    border-color 180ms ease;
}

.profile-button:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-soft);
}

.profile-button__avatar {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: rgba(163, 18, 25, 0.1);
  color: var(--color-red);
  font-weight: 700;
}

.profile-button__copy {
  display: grid;
  text-align: left;
}

.profile-button__copy strong {
  font-size: 0.94rem;
}

.profile-button__copy small {
  color: var(--color-text-soft);
  font-size: 0.78rem;
}

@media (max-width: 980px) {
  .topbar {
    grid-template-columns: 1fr;
    justify-items: stretch;
  }

  .topbar__nav {
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  .topbar__actions {
    flex-wrap: wrap;
  }
}
</style>
