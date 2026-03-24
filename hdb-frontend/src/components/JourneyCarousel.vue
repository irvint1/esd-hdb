<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { JourneySlide } from '../data/home'

const props = defineProps<{
  slides: JourneySlide[]
}>()

const activeIndex = ref(0)
let timer: number | undefined

const activeSlide = computed(() => props.slides[activeIndex.value] ?? props.slides[0]!)

function nextSlide() {
  activeIndex.value = (activeIndex.value + 1) % props.slides.length
}

function previousSlide() {
  activeIndex.value = (activeIndex.value - 1 + props.slides.length) % props.slides.length
}

function goToSlide(index: number) {
  activeIndex.value = index
}

function startAutoplay() {
  stopAutoplay()
  timer = window.setInterval(() => {
    nextSlide()
  }, 6500)
}

function stopAutoplay() {
  if (timer) {
    window.clearInterval(timer)
  }
}

onMounted(() => {
  startAutoplay()
})

onBeforeUnmount(() => {
  stopAutoplay()
})
</script>

<template>
  <section
    class="journey card-surface"
    id="journey"
    @mouseenter="stopAutoplay"
    @mouseleave="startAutoplay"
  >
    <p class="section-tag">BTO journey</p>
    <div class="journey__head">
      <div>
        <h3>{{ activeSlide.title }}</h3>
        <p>{{ activeSlide.summary }}</p>
      </div>
      <span class="journey__stage">{{ activeSlide.stage }}</span>
    </div>

    <div class="journey__visual">
      <div class="journey__metric">
        <strong>{{ activeSlide.metric }}</strong>
        <span>{{ activeSlide.metricLabel }}</span>
      </div>
      <div class="journey__grid">
        <span></span>
        <span></span>
        <span></span>
        <span></span>
        <span></span>
        <span></span>
      </div>
    </div>

    <ul class="journey__bullets">
      <li v-for="bullet in activeSlide.bullets" :key="bullet">{{ bullet }}</li>
    </ul>

    <div class="journey__controls">
      <button class="button button--ghost" type="button" @click="previousSlide">Previous</button>
      <div class="journey__dots">
        <button
          v-for="(slide, index) in slides"
          :key="slide.id"
          type="button"
          :class="{ 'is-active': index === activeIndex }"
          :aria-label="`Show journey slide ${index + 1}`"
          @click="goToSlide(index)"
        ></button>
      </div>
      <button class="button button--ghost" type="button" @click="nextSlide">Next</button>
    </div>
  </section>
</template>

<style scoped>
.journey {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding: 28px;
}

.journey__head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.journey__head h3 {
  margin: 0;
  font-size: clamp(1.6rem, 2.2vw, 2.35rem);
  line-height: 1.05;
  letter-spacing: -0.04em;
}

.journey__head p {
  margin: 14px 0 0;
  color: var(--color-text-muted);
  line-height: 1.7;
}

.journey__stage {
  align-self: flex-start;
  padding: 10px 14px;
  border-radius: 999px;
  background: rgba(163, 18, 25, 0.08);
  color: var(--color-red);
  font-size: 0.84rem;
  font-weight: 700;
  white-space: nowrap;
}

.journey__visual {
  display: grid;
  grid-template-columns: minmax(180px, 0.8fr) minmax(200px, 1fr);
  gap: 16px;
  align-items: stretch;
}

.journey__metric,
.journey__grid {
  border: 1px solid var(--color-border);
  border-radius: 24px;
  background: var(--color-surface-alt);
}

.journey__metric {
  display: grid;
  align-content: center;
  gap: 6px;
  padding: 22px;
}

.journey__metric strong {
  font-size: 2rem;
  letter-spacing: -0.05em;
}

.journey__metric span {
  color: var(--color-text-muted);
  line-height: 1.6;
}

.journey__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 18px;
}

.journey__grid span {
  min-height: 66px;
  border-radius: 18px;
  background:
    linear-gradient(180deg, rgba(163, 18, 25, 0.1), rgba(163, 18, 25, 0.03));
  border: 1px solid rgba(163, 18, 25, 0.08);
}

.journey__grid span:nth-child(2),
.journey__grid span:nth-child(5) {
  min-height: 98px;
}

.journey__grid span:nth-child(3),
.journey__grid span:nth-child(4) {
  min-height: 82px;
}

.journey__bullets {
  display: grid;
  gap: 12px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.journey__bullets li {
  position: relative;
  padding-left: 20px;
  color: var(--color-text);
  line-height: 1.65;
}

.journey__bullets li::before {
  content: '';
  position: absolute;
  top: 10px;
  left: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-red);
}

.journey__controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: auto;
}

.journey__dots {
  display: flex;
  gap: 10px;
}

.journey__dots button {
  width: 11px;
  height: 11px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(23, 23, 23, 0.14);
  cursor: pointer;
}

.journey__dots .is-active {
  background: var(--color-red);
}

@media (max-width: 720px) {
  .journey__head,
  .journey__controls {
    flex-direction: column;
    align-items: stretch;
  }

  .journey__visual {
    grid-template-columns: 1fr;
  }

  .journey__stage {
    white-space: normal;
  }
}
</style>
