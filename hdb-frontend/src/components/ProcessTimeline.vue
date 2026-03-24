<script setup lang="ts">
import type { ProcessStep } from '../data/home'

defineProps<{
  steps: ProcessStep[]
}>()
</script>

<template>
  <section class="timeline">
    <article v-for="step in steps" :key="step.id" class="timeline__card card-surface">
      <span class="timeline__label">{{ step.label }}</span>
      <h3>{{ step.title }}</h3>
      <p>{{ step.detail }}</p>
    </article>
  </section>
</template>

<style scoped>
.timeline {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
  max-width: 1240px;
  margin: 24px auto 0;
}

.timeline__card {
  padding: 22px;
}

.timeline__label {
  display: inline-block;
  margin-bottom: 14px;
  color: var(--color-red);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.timeline__card h3 {
  margin: 0;
  font-size: 1.24rem;
  letter-spacing: -0.03em;
}

.timeline__card p {
  margin: 12px 0 0;
  color: var(--color-text-muted);
  line-height: 1.7;
}

@media (max-width: 980px) {
  .timeline {
    grid-template-columns: 1fr;
  }
}
</style>
