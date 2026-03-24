<script setup lang="ts">
import type { LaunchItem } from '../data/home'

defineProps<{
  launches: LaunchItem[]
}>()
</script>

<template>
  <section class="launches" id="launches">
    <div class="section-header">
      <div>
        <p class="section-tag">Upcoming BTO launches</p>
        <h2>Plan ahead with launch windows, flat mix, and cleaner launch summaries.</h2>
      </div>
      <p class="section-header__note">
        A more professional launch board keeps the key facts visible without turning the page into
        a promotional brochure.
      </p>
    </div>

    <div class="launches__grid">
      <article v-for="launch in launches" :key="launch.id" class="launch-card card-surface">
        <div class="launch-card__header">
          <div>
            <p class="launch-card__month">{{ launch.month }}</p>
            <h3>{{ launch.project }}</h3>
          </div>
          <span class="launch-card__status">{{ launch.status }}</span>
        </div>

        <strong class="launch-card__town">{{ launch.town }}</strong>
        <p class="launch-card__summary">{{ launch.summary }}</p>

        <div class="launch-card__chips">
          <span v-for="flatType in launch.flatTypes" :key="flatType">{{ flatType }}</span>
        </div>

        <div class="launch-card__footer">
          <span>Application milestone</span>
          <strong>{{ launch.window }}</strong>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.launches {
  max-width: 1240px;
  margin: 0 auto;
  padding-top: 80px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: end;
  margin-bottom: 22px;
}

.section-header h2 {
  margin: 0;
  font-size: clamp(2rem, 3vw, 3rem);
  line-height: 0.98;
  letter-spacing: -0.045em;
}

.section-header__note {
  max-width: 420px;
  margin: 0;
  color: var(--color-text-muted);
  line-height: 1.7;
}

.launches__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}

.launch-card {
  padding: 24px;
}

.launch-card__header {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: start;
}

.launch-card__month {
  margin: 0 0 8px;
  color: var(--color-text-soft);
  font-size: 0.84rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.launch-card h3 {
  margin: 0;
  font-size: 1.44rem;
  line-height: 1.04;
  letter-spacing: -0.04em;
}

.launch-card__status {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(163, 18, 25, 0.08);
  color: var(--color-red);
  font-size: 0.8rem;
  font-weight: 700;
  white-space: nowrap;
}

.launch-card__town {
  display: block;
  margin-top: 16px;
  color: var(--color-red);
  font-size: 0.94rem;
}

.launch-card__summary {
  margin: 14px 0 0;
  color: var(--color-text-muted);
  line-height: 1.72;
}

.launch-card__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 22px 0 24px;
}

.launch-card__chips span {
  padding: 8px 12px;
  border-radius: 999px;
  background: var(--color-surface-alt);
  color: var(--color-text);
  font-size: 0.82rem;
}

.launch-card__footer {
  display: grid;
  gap: 6px;
  padding-top: 18px;
  border-top: 1px solid var(--color-border);
}

.launch-card__footer span {
  color: var(--color-text-soft);
  font-size: 0.82rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.launch-card__footer strong {
  font-size: 0.96rem;
}

@media (max-width: 1080px) {
  .section-header {
    flex-direction: column;
    align-items: start;
  }

  .launches__grid {
    grid-template-columns: 1fr;
  }
}
</style>
